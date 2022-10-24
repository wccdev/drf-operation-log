import ast
from collections.abc import MutableMapping

from django.db.models import Manager
from rest_framework.fields import BooleanField, ChoiceField
from rest_framework.serializers import Serializer

attribute_sep = ">"
missing_value = object()

CLEANED_SUBSTITUTE = "********************"
sensitive_fields = {}


def split_get(o: object, concat_attr: str, sep: str = attribute_sep):
    for attr in concat_attr.split(sep):
        try:
            o = getattr(o, attr)
        except AttributeError:
            return missing_value

    return o


def _get_source_fields(fields):
    return {f.source: f for f in fields.values() if f.source != "*"}


def _flatten_dict_gen(d, parent_key, sep):
    for k, v in d.items():
        if getattr(v, "read_only", False):
            continue

        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, MutableMapping):
            yield from flatten_dict(v, new_key, sep=sep).items()
        elif isinstance(v, Serializer):
            yield from flatten_dict(
                _get_source_fields(v.fields), new_key, sep=sep
            ).items()
        else:
            yield new_key, v


def flatten_dict(d: MutableMapping, parent_key: str = "", sep: str = attribute_sep):
    return dict(_flatten_dict_gen(d, parent_key, sep))


def serializer_data_diff(old_data: dict, new_data: dict, serializer: Serializer) -> dict:
    """
    判断两个个序列化器校验后数据数据差异
    :return:
    """
    trans_dic = flatten_dict(_get_source_fields(serializer.fields))

    ret = {}

    for (k_old, v_old), (k_new, v_new) in zip(old_data.items(), new_data.items()):
        if k_old != k_new:
            raise ValueError("比较的数据key顺序错误")

        try:
            field = trans_dic[k_new]
            label = field.label or k_new
            if isinstance(field, ChoiceField):
                v_mapping = dict(field.choices)
                v_old = v_mapping.get(v_old) or v_old
                v_new = v_mapping.get(v_new) or v_new
            elif isinstance(v_old, Manager):
                v_old = list(v_old.all())
            elif isinstance(field, BooleanField):
                v_old = "是" if v_old else "否"
                v_new = "是" if v_new else "否"

            if v_old == v_new or v_old == missing_value:
                continue

            ret[label] = [v_old, v_new]
        except KeyError:
            pass
    return ret


def clean_data(data, sensitive_fields=None):
    """
    Clean a dictionary of data of potentially sensitive info before
    sending to the database.
    Function based on the "_clean_credentials" function of django
    (https://github.com/django/django/blob/stable/1.11.x/django/contrib/auth/__init__.py#L50)
    Fields defined by django are by default cleaned with this function
    You can define your own sensitive fields in your view by defining a set
    eg: sensitive_fields = {'field1', 'field2'}
    """
    sensitive_fields = sensitive_fields or {}

    if isinstance(data, bytes):
        data = data.decode(errors="replace")

    if isinstance(data, list):
        return [clean_data(d) for d in data]

    if isinstance(data, dict):
        SENSITIVE_FIELDS: set = {
            "api",
            "token",
            "key",
            "secret",
            "password",
            "signature",
        }

        data = dict(data)
        if sensitive_fields:
            SENSITIVE_FIELDS = SENSITIVE_FIELDS | {
                field.lower() for field in sensitive_fields
            }

        for key, value in data.items():
            try:
                value = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                pass
            if isinstance(value, (list, dict)):
                data[key] = clean_data(value)
            if key.lower() in SENSITIVE_FIELDS:
                data[key] = CLEANED_SUBSTITUTE
    return data
