#migrate


from api.dwarf_backup_db import DB_NAME, connect_db, close_db, commit_db
from api.dwarf_backup_db import add_column_if_not_exists, migrate_table_auto_add_fk_column

conn = connect_db(DB_NAME)

add_column_if_not_exists(conn, "AstroObject", "is_group", "BOOLEAN DEFAULT 0")

migrate_table_auto_add_fk_column(
    conn,
    table_name="DwarfEntry",
    new_column_name="astro_group_id",
    new_column_type="INTEGER",
    fk_reference_table="AstroObject",
    fk_reference_column="id",
    on_delete_action="SET NULL"  # <- foreign key will nullify if the group is deleted
)
migrate_table_auto_add_fk_column(
    conn,
    table_name="BackupEntry",
    new_column_name="astro_group_id",
    new_column_type="INTEGER",
    fk_reference_table="AstroObject",
    fk_reference_column="id",
    on_delete_action="SET NULL"  # <- foreign key will nullify if the group is deleted
)
commit_db(conn)
close_db(conn)