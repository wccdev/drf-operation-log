import json

from django.conf import settings
from django.contrib.admin.utils import quote
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.text import get_text_list
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from .encoders import JSONEncoder

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

    def log_operation(
        self,
        user,
        action,
        action_name,
        action_flag,
        instance,
        old_message=None,
        new_message=None,
        change_message=None,
        serializer=None,
        save_db=True,
    ) -> None:

        if action_flag == CHANGE and change_message is None:
            change_message = serializer_data_diff(serializer, old_message, new_message)

        operation_log = self.model(
            user=user,
            action=action,
            action_name=action_name,
            action_flag=action_flag,
            content_type=ContentType.objects.get_for_model(instance),
            object_id=instance.pk,
            change_message=change_message or {},
        )
        if save_db:
            operation_log.save()

        return operation_log


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
        blank=True,
        null=True,
    )
    object_id = models.TextField(_("对象ID"), blank=True, null=True)
    action = models.CharField(_("动作"), max_length=32)
    action_name = models.CharField(_("动作名称"), max_length=32)
    action_flag = models.PositiveSmallIntegerField(_("操作类型"), choices=ACTION_FLAG_CHOICES)
    change_message = models.JSONField(_("差异信息"), blank=True, default=dict, encoder=JSONEncoder)

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

    def get_edited_object(self):
        """Return the edited object represented by this log entry."""
        return self.content_type.get_object_for_this_type(pk=self.object_id)

    def get_operation_url(self):
        """
        Return the admin URL to edit the object represented by this log entry.
        """
        if self.content_type and self.object_id:
            url_name = "admin:%s_%s_change" % (
                self.content_type.app_label,
                self.content_type.model,
            )
            try:
                return reverse(url_name, args=(quote(self.object_id),))
            except NoReverseMatch:
                pass
        return None
