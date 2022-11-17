import json

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .encoders import JSONEncoder
from .utils import clean_data

ADDITION = 1
CHANGE = 2
DELETION = 3

ACTION_FLAG_CHOICES = (
    (ADDITION, _("Addition")),
    (CHANGE, _("Change")),
    (DELETION, _("Deletion")),
)


class OperationLogEntryManager(models.Manager):
    use_in_migrations = True

    def log_action(
        self,
        user_id,
        content_type_id,
        object_id,
        object_repr,
        action_flag,
        change_message="",
    ):
        change_message = clean_data(change_message)
        if isinstance(change_message, list):
            change_message = json.dumps(change_message)

        return self.model.objects.create(
            user_id=user_id,
            content_type_id=content_type_id,
            object_id=str(object_id),
            object_repr=object_repr[:200],
            action_flag=action_flag,
            change_message=change_message,
        )


class OperationLogEntry(models.Model):
    action_time = models.DateTimeField(
        _("操作时间"),
        default=timezone.now,
        db_index=True,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        models.CASCADE,
        verbose_name=_("用户"),
    )
    content_type = models.ForeignKey(
        ContentType,
        models.SET_NULL,
        verbose_name=_("操作对象"),
        related_name="+",
        blank=True,
        null=True,
    )
    object_id = models.TextField(_("对象ID"), blank=True, null=True)
    object_repr = models.CharField(_("操作对象"), max_length=128)
    domain_content_type = models.ForeignKey(
        ContentType,
        models.SET_NULL,
        verbose_name=_("同范围操作对象"),
        related_name="+",
        blank=True,
        null=True,
    )
    domain_object_id = models.TextField(_("同范围对象ID"), blank=True, null=True)
    action = models.CharField(_("动作"), max_length=32)
    action_name = models.CharField(_("动作名称"), max_length=32)
    action_flag = models.PositiveSmallIntegerField(
        _("操作类型"), choices=ACTION_FLAG_CHOICES
    )
    change_message = models.JSONField(
        _("差异信息"), blank=True, default=dict, encoder=JSONEncoder
    )
    extra = models.JSONField(_("其他信息"), blank=True, null=True)

    objects = OperationLogEntryManager()

    class Meta:
        verbose_name = verbose_name_plural = _("操作日志")
        db_table = "drf_operation_log"
        ordering = ["-action_time"]
        index_together = ("content_type", "object_id")

    def __repr__(self):
        return str(self.action_time)

    def __str__(self):
        if self.is_addition():
            return gettext("新增 “%(object)s”.") % {"object": self.object_repr}
        elif self.is_change():
            return gettext("修改 “%(object)s” — %(changes)s") % {
                "object": self.object_repr,
                "changes": self.get_change_message(),
            }
        elif self.is_deletion():
            return gettext("删除 “%(object)s.”") % {"object": self.object_repr}

        return gettext("LogEntry Object")

    def is_addition(self):
        return self.action_flag == ADDITION

    def is_change(self):
        return self.action_flag == CHANGE

    def is_deletion(self):
        return self.action_flag == DELETION

    def get_change_message(self):
        """
        If self.change_message is a JSON structure, interpret it as a change
        string, properly translated.
        """
        # if self.is_addition():
        #     return [f"新增 {self.object_repr}"]
        # elif self.is_deletion():
        #     return [f"删除 {self.object_repr}"]
        # elif not self.change_message:
        #     return ["未更改"]

        # ret = []
        # for field_name, (old_value, new_value) in self.change_message.items():
        #     old_value = "" if old_value is None else old_value
        #     new_value = "" if new_value is None else new_value
        #     message = f"修改 {field_name}， 旧值“{old_value}”，新值“{new_value}”"
        #     ret.append(message)

        return self.change_message

    def get_edited_object(self):
        """Return the edited object represented by this log entry."""
        return self.content_type.get_object_for_this_type(pk=self.object_id)

    def get_operation_url(self):
        """
        Return the admin URL to edit the object represented by this log entry.
        """
        if self.content_type and self.object_id:
            url_name = "operationlogs-list"
            try:
                url = reverse(url_name)
                return (
                    f"{url}?content_type={self.content_type.pk}"
                    "&object_id={self.object_id}"
                )
            except NoReverseMatch:
                pass
        return None
