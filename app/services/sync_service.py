from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import Listing, ExternalListing, SourceAccount, SyncRun
from app.integrations.catalog_source import SourcePage

class SyncConflict(Exception):
    pass

class InvalidSnapshot(Exception):
    pass

def synchronize(session_factory, source_id, owner_id, adapter):
    # Committed running row locks one account across processes, on both DBs.
    with session_factory() as db:
        account = db.scalar(select(SourceAccount).where(SourceAccount.id == source_id, SourceAccount.owner_id == owner_id))
        if account is None:
            raise LookupError('Source account not found')
        platform, account_id = account.platform, account.account_id
        run = SyncRun(source_id=source_id, status='running')
        db.add(run)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise SyncConflict('Synchronization already running') from exc
        run_id = run.id
    try:
        items = {}
        complete = False
        for page_number, raw_page in enumerate(adapter.pages(), start=1):
            if complete or page_number > 10000:
                raise InvalidSnapshot('Invalid page sequence')
            page = SourcePage.model_validate(raw_page)
            for item in page.items:
                if item.external_id in items:
                    raise InvalidSnapshot('Duplicate external ID in snapshot')
                items[item.external_id] = item
                if len(items) > 100000:
                    raise InvalidSnapshot('Snapshot size exceeded')
            complete = page.complete
        if not complete:
            raise InvalidSnapshot('Full snapshot not received')
        now = datetime.now(timezone.utc)
        with session_factory() as db:
            with db.begin():
                account = db.get(SourceAccount, source_id)
                if account is None or account.owner_id != owner_id:
                    raise InvalidSnapshot('Source owner changed')
                links = {link.external_id: link for link in db.scalars(select(ExternalListing).where(ExternalListing.platform == platform, ExternalListing.account_id == account_id))}
                for external_id, item in items.items():
                    link = links.get(external_id)
                    if link:
                        listing = db.get(Listing, link.listing_id)
                        if listing is None or listing.owner_id != owner_id:
                            raise InvalidSnapshot('Catalog ownership mismatch')
                        listing.title, listing.price = item.title, item.price
                        if item.description is not None:
                            listing.description = item.description
                        # Keep manually assigned brand, size, condition and local status.
                    else:
                        listing = Listing(owner_id=owner_id, title=item.title, description=item.description or '', price=item.price, status=item.catalog_status)
                        db.add(listing)
                        db.flush()
                        link = ExternalListing(listing_id=listing.id, platform=platform, account_id=account_id, external_id=external_id)
                        db.add(link)
                    link.url = str(item.url) if item.url else None
                    link.external_status = item.external_status
                    link.source_data = item.model_dump(mode='json')
                    link.source_present = True
                    link.synced_at = now
                for external_id, link in links.items():
                    if external_id not in items:
                        link.source_present = False
                run = db.get(SyncRun, run_id)
                run.status, run.finished_at, run.imported = 'succeeded', now, len(items)
        return run_id
    except Exception as exc:
        with session_factory() as db:
            run = db.get(SyncRun, run_id)
            run.status = 'failed'
            run.finished_at = datetime.now(timezone.utc)
            # Never store API response bodies, credentials or exception messages.
            run.error_code = 'invalid_snapshot' if isinstance(exc, InvalidSnapshot) else 'source_failure'
            db.commit()
        raise
