
from django.db import migrations

FORWARDS = """
CREATE OR REPLACE FUNCTION vault_audit_block_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'vault_auditevent is append-only'
        USING ERRCODE = 'insufficient_privilege';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS vault_audit_append_only ON vault_auditevent;
CREATE TRIGGER vault_audit_append_only
    BEFORE UPDATE OR DELETE ON vault_auditevent
    FOR EACH ROW EXECUTE FUNCTION vault_audit_block_change();
"""

BACKWARDS = """
DROP TRIGGER IF EXISTS vault_audit_append_only ON vault_auditevent;
DROP FUNCTION IF EXISTS vault_audit_block_change();
"""


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(FORWARDS)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(BACKWARDS)


class Migration(migrations.Migration):
    dependencies = [
        ("vault", "0006_auditchainhead_alter_auditevent_options_and_more"),
    ]

    operations = [
        migrations.RunPython(install, uninstall),
    ]
