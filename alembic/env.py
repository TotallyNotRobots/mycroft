import logging

from alembic import context

from cloudbot.bot import CloudBot
from cloudbot.util import database

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    bot: CloudBot | None = config.attributes.get("bot")
    if bot is None:
        bot = CloudBot(create_connections=False)
        # Only load tables if we create the bot, otherwise assume they were loaded
        # by whoever called us
        bot.plugin_manager.get_plugin_tables(bot.plugin_dir)

    target_metadata = database.metadata

    connectable = bot.db_engine

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


def setup_logging() -> None:
    cb_logger = logging.getLogger("cloudbot")
    for handler in cb_logger.handlers:
        if handler.name == "console":
            handler.setLevel(logging.WARNING)


if __name__ == "env_py":
    setup_logging()
    run_migrations_online()
