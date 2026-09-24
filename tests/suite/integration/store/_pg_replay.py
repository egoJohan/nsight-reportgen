"""The data half of `datahive restore --with-data`, run INSIDE the hive container.

Two calls, the same two the fixed CLI makes: extract the Postgres plane out of
the archive, then replay it in one transaction. The CLI itself is not used
because the image this hive runs dies in the step before them — it calls its
own `backup` command as a plain function and the untouched Typer option
arrives as an `OptionInfo` ("TypeError: str expected, not OptionInfo"). That is
fixed in egohive's source and not in the image, and the test needs the restore
it guards, not the wrapper.

Copied into the container by the test; not imported by anything here.
"""
import asyncio
import os
import sys
from pathlib import Path

from hive.backup.restores import restore_pg
from hive.cli.commands.backup import build_backup_service_from_config
from hive.config import load_config

src, cfg_path, state_dir = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
passphrase = os.environ["DHBAK_PASS"].strip()

service = build_backup_service_from_config(cfg_path, state_dir)
scratch = src.parent / f".{src.name}.replay"
scratch.mkdir(parents=True, exist_ok=True)
pg_path = scratch / "pg.sql"
try:
    asyncio.run(service.extract_plane(src, "pg", pg_path, passphrase=passphrase))
    config = load_config(cfg_path)
    applied = restore_pg(config.storage.relational.dsn, pg_path.read_bytes(),
                         target_schema=config.storage.relational.schema_name)
    print(f"postgres restored: {applied} bytes applied")
finally:
    for leftover in scratch.glob("*"):
        leftover.unlink(missing_ok=True)
    scratch.rmdir()
