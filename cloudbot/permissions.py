import logging
from typing import cast

from irclib.util.compare import match_mask
from sqlalchemy import Boolean, Column, ForeignKeyConstraint, String, select
from sqlalchemy.orm import relationship

from cloudbot.util import database
from cloudbot.util.database import Session

logger = logging.getLogger("cloudbot")

# put your hostmask here for magic
# it's disabled by default, see has_perm_mask()
backdoor: str | None = None


class Group(database.Base):
    __tablename__ = "perm_group"

    connection = Column(String, nullable=False, primary_key=True)
    name = Column(String, nullable=False, primary_key=True)
    members = relationship("GroupMember", back_populates="group", uselist=True)
    perms = relationship(
        "GroupPermission", back_populates="group", uselist=True
    )

    config = Column(Boolean, default=False)

    def is_member(self, mask: str) -> bool:
        for member in self.members:
            if member.match(mask):
                return True

        return False

    def has_perm(self, name: str) -> bool:
        for perm in self.perms:
            if perm.match(name):
                return True

        return False


class GroupMember(database.Base):
    __tablename__ = "group_member"

    connection = Column(String, nullable=False, primary_key=True)
    group_id = Column(String, primary_key=True)

    group = relationship(Group, back_populates="members", uselist=False)

    mask = Column(String, primary_key=True, nullable=False)

    config = Column(Boolean, default=False)

    __table_args__ = (
        ForeignKeyConstraint(
            [group_id, connection],
            [Group.name, Group.connection],
            "group_member_group_fk",
        ),
    )

    def match(self, user: str) -> bool:
        return match_mask(user.lower(), self.mask)


class GroupPermission(database.Base):
    __tablename__ = "group_perm"

    connection = Column(String, nullable=False, primary_key=True)
    group_id = Column(String, primary_key=True)
    group = relationship(Group, back_populates="perms", uselist=False)

    name = Column(String, primary_key=True, nullable=False)

    config = Column(Boolean, default=False)

    __table_args__ = (
        ForeignKeyConstraint(
            [group_id, connection],
            [Group.name, Group.connection],
            "group_perm_group_fk",
        ),
    )

    def match(self, name: str) -> bool:
        return bool(self.name == name.lower())


class PermissionManager:
    def __init__(self, conn) -> None:
        logger.info(
            "[%s|permissions] Created permission manager for %s.",
            conn.name,
            conn.name,
        )

        self.name = conn.name
        self.config = conn.config

        session = Session()
        Group.__table__.create(session.bind, checkfirst=True)
        GroupPermission.__table__.create(session.bind, checkfirst=True)
        GroupMember.__table__.create(session.bind, checkfirst=True)

        self.reload()

    def reload(self) -> None:
        session = Session()

        updated = []
        for group_id, data in self.config.get("permissions", {}).items():
            group = self.get_group(group_id)
            if not group:
                group = Group(
                    connection=self.name.lower(), name=group_id.lower()
                )
                session.add(group)

            group.config = True
            updated.append(group)

            for user in data["users"]:
                member = session.get(
                    GroupMember,
                    {
                        "group_id": group_id.lower(),
                        "mask": user.lower(),
                        "connection": self.name.lower(),
                    },
                )
                if not member:
                    member = GroupMember(
                        group_id=group_id.lower(),
                        mask=user.lower(),
                        connection=self.name.lower(),
                    )
                    session.add(member)

                member.config = True
                updated.append(member)

            for perm in data["perms"]:
                binding = session.get(
                    GroupPermission,
                    {
                        "group_id": group_id.lower(),
                        "name": perm.lower(),
                        "connection": self.name.lower(),
                    },
                )
                if not binding:
                    binding = GroupPermission(
                        group_id=group_id.lower(),
                        name=perm.lower(),
                        connection=self.name.lower(),
                    )
                    session.add(binding)

                binding.config = True
                updated.append(binding)

        session.commit()

        for item in (
            session.query(GroupMember)
            .filter_by(config=True, connection=self.name.lower())
            .all()
        ):
            if item not in updated:
                session.delete(item)

        for item in (
            session.query(GroupPermission)
            .filter_by(config=True, connection=self.name.lower())
            .all()
        ):
            if item not in updated:
                session.delete(item)

        for item in (
            session.query(Group)
            .filter_by(config=True, connection=self.name.lower())
            .all()
        ):
            if item not in updated:
                session.delete(item)

        session.commit()

    def has_perm_mask(
        self, user_mask: str, perm: str, notice: bool = True
    ) -> bool:
        if backdoor and match_mask(user_mask.lower(), backdoor.lower()):
            return True

        if perm.lower() in self.get_user_permissions(user_mask):
            if notice:
                logger.info(
                    "[%s|permissions] Allowed user %s access to %s",
                    self.name,
                    user_mask,
                    perm,
                )

            return True

        return False

    def get_perm_users(self, perm: str):
        return [
            member.mask
            for group in self.get_perm_groups(perm)
            for member in group.members
        ]

    def get_perm_groups(self, perm: str):
        return [group for group in self.get_groups() if group.has_perm(perm)]

    def get_groups(self):
        return (
            Session()
            .execute(select(Group).where(Group.connection == self.name.lower()))
            .scalars()
            .all()
        )

    def get_group_permissions(self, name: str) -> list[str]:
        group = self.get_group(name)
        if not group:
            return []

        return [perm.name for perm in group.perms]

    def get_group_users(self, name: str) -> list[str]:
        group = self.get_group(name)
        if not group:
            return []

        return [member.mask for member in group.members]

    def get_user_permissions(self, user_mask: str) -> set[str]:
        return {
            perm.name
            for group in self.get_user_groups(user_mask)
            for perm in group.perms
        }

    def get_user_groups(self, user_mask: str) -> list[Group]:
        return [
            group for group in self.get_groups() if group.is_member(user_mask)
        ]

    def get_group(self, group_id: str) -> Group | None:
        return cast(
            Group | None,
            Session().get(
                Group,
                {"name": group_id.lower(), "connection": self.name.lower()},
            ),
        )

    def get_or_create_group(self, group_id: str):
        return self.add_group(group_id, check_first=True)

    def add_group(self, group_id: str, *, check_first: bool = False) -> Group:
        if check_first:
            if group := self.get_group(group_id):
                return group

        session = Session()
        group = Group(connection=self.name.lower(), name=group_id.lower())
        session.add(group)
        session.commit()
        return group

    def group_exists(self, group: str) -> bool:
        """
        Checks whether a group exists
        """
        return self.get_group(group) is not None

    def user_in_group(self, user_mask: str, group_id: str):
        """
        Checks whether a user is matched by any masks in a given group
        """
        group = self.get_group(group_id)
        if not group:
            return False

        return group.is_member(user_mask)

    def remove_group_user(self, group_id: str, user_mask: str):
        """
        Removes all users that match user_mask from group. Returns a list of user masks removed from the group.
        """
        group = self.get_group(group_id)
        if not group:
            return []

        masks_removed = []

        session = Session()
        for member in group.members:
            mask_to_check = member.mask
            if member.match(user_mask):
                masks_removed.append(mask_to_check)
                session.delete(member)

        session.commit()

        return masks_removed

    def add_user_to_group(self, user_mask: str, group_id: str) -> bool:
        """
        Adds user to group. Returns whether this actually did anything.
        """
        if self.user_in_group(user_mask, group_id):
            return False

        group = self.get_or_create_group(group_id)
        session = Session()

        session.add(
            GroupMember(
                mask=user_mask,
                group=group,
                connection=self.name.lower(),
            )
        )

        session.commit()

        return True
