from django.db import migrations


class Migration(migrations.Migration):
    """
    Supprime la contrainte FK django_admin_log → bank_user.
    En mode pgbouncer transaction (Supabase/Vercel), cette contrainte DEFERRABLE
    provoque un IntegrityError au COMMIT même quand l'utilisateur existe,
    causant un rollback de toute l'opération admin.
    L'intégrité référentielle est assurée par Django, pas nécessaire en DB.
    """

    dependencies = [
        ('accounts', '0003_security_constraints_and_indexes'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            ALTER TABLE django_admin_log
            DROP CONSTRAINT IF EXISTS django_admin_log_user_id_fk_bank_user;
            """,
            reverse_sql=migrations.RunSQL.noop,
        )
    ]
