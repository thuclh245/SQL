from alembic import context

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=context.config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    raise RuntimeError("Database migration engine is not configured in P0.")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
