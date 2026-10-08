"""Copy a consistent SQLite snapshot into an empty, migrated database."""
import argparse
import sqlite3
import tempfile
from pathlib import Path
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine, select, text
from app.database import Base, engine
from app import models

class TransferError(Exception):
    pass

def canonical(value):
    if isinstance(value,datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value,Decimal):
        return value.normalize()
    return value

def fingerprint(rows):
    return [[canonical(value) for value in row] for row in rows]

def transfer(source_path,target_engine,apply=False):
    source_path=Path(source_path).resolve(strict=True)
    if target_engine.dialect.name=='sqlite' and Path(target_engine.url.database).resolve()==source_path:
        raise TransferError('Source and target must differ')
    tables=Base.metadata.sorted_tables
    with tempfile.TemporaryDirectory() as folder:
        snapshot=Path(folder)/'snapshot.db'
        with closing(sqlite3.connect(source_path.as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(snapshot)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or dst.execute('PRAGMA foreign_key_check').fetchall():
                raise TransferError('Source integrity check failed')
        source=create_engine(f'sqlite:///{snapshot}',hide_parameters=True)
        try:
            with source.connect() as src, target_engine.connect() as dst:
                expected=src.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
                actual=dst.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
                if sorted(expected)!=sorted(actual):
                    raise TransferError('Source and target migrations must match')
                # End the schema-check transaction before the transfer transaction.
                dst.rollback()
                transaction=dst.begin()
                try:
                    if target_engine.dialect.name=='postgresql':
                        names=', '.join(target_engine.dialect.identifier_preparer.quote(t.name) for t in tables)
                        dst.execute(text('LOCK TABLE '+names+' IN ACCESS EXCLUSIVE MODE'))
                    for table in tables:
                        if dst.execute(select(table).limit(1)).first() is not None:
                            raise TransferError('Target must be empty; existing data will not be overwritten')
                    counts={}
                    for table in tables:
                        rows=src.execute(select(table).order_by(table.c.id)).all()
                        if rows:
                            dst.execute(table.insert(),[dict(row._mapping) for row in rows])
                        copied=dst.execute(select(table).order_by(table.c.id)).all()
                        if fingerprint(rows)!=fingerprint(copied):
                            raise TransferError('Copied data verification failed')
                        counts[table.name]=len(rows)
                    if target_engine.dialect.name=='postgresql' and apply:
                        for table in tables:
                            # Only known ORM table names are used. Reset IDs for future inserts.
                            quoted=target_engine.dialect.identifier_preparer.quote(table.name)
                            dst.execute(text("SELECT setval(pg_get_serial_sequence(:name, 'id'), COALESCE((SELECT MAX(id) FROM "+quoted+"), 1), EXISTS(SELECT 1 FROM "+quoted+"))"),{'name':table.name})
                    if apply:
                        transaction.commit()
                    else:
                        transaction.rollback()
                    return counts
                except Exception:
                    transaction.rollback()
                    raise
        finally:
            source.dispose()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--apply',action='store_true',help='Commit after verification; default is dry run')
    args=parser.parse_args()
    if engine.dialect.name!='postgresql':
        raise SystemExit('Configure a PostgreSQL target; source SQLite is never modified')
    try:
        counts=transfer(args.source,engine,args.apply)
    except Exception as exc:
        # Avoid printing SQL, rows or credential-bearing URLs.
        raise SystemExit('Transfer failed: '+(str(exc) if isinstance(exc,TransferError) else type(exc).__name__))
    print('Transfer committed' if args.apply else 'Dry run passed; target unchanged')
    print('Rows checked:',sum(counts.values()))

if __name__=='__main__':
    main()
