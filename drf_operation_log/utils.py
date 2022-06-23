from collections.abc import MutableMapping

from django.db.models import Manager
from rest_framework.fields import ChoiceField, BooleanField
from rest_framework.serializers import Serializer

attribute_sep = ">"
missing_value = object()


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
            yield from flatten_dict(_get_source_fields(v.fields), new_key, sep=sep).items()
        else:
            yield new_key, v


def flatten_dict(d: MutableMapping, parent_key: str = "", sep: str = attribute_sep):
    """
    将字典平铺
    {"nested": {"a": 1}} -> {"nested>a": 1}
    """
    return dict(_flatten_dict_gen(d, parent_key, sep))


def serializer_data_diff(
    serializer: Serializer,
    old_data: dict = None,
    new_data: dict = None,
) -> dict:
    """
    判断两个个序列化器校验后数据数据差异
    :return:
    """
    trans_dic = flatten_dict(_get_source_fields(serializer.fields))

    if new_data is None:
        new_data = flatten_dict(serializer.validated_data)

    if old_data is None:
        old_data = {}
        for k in new_data.keys():
            old_data[k] = split_get(serializer.instance, k)

    diff_message = {}
    for (k_old, v_old), (k_new, v_new) in zip(old_data.items(), new_data.items()):
        if k_old != k_new:
            raise ValueError("比较的数据key顺序错误")

        try:
            field = trans_dic[k_new]
        except KeyError:
            continue

        label = field.label or k_new
        if isinstance(field, ChoiceField):
            v_mapping = dict(field.choices)
            v_old = v_mapping.get(v_old, v_old)
            v_new = v_mapping.get(v_new, v_new)
        elif isinstance(v_old, Manager):
            v_old = tuple(v_old.all())
        elif isinstance(field, BooleanField):
            v_old = "是" if v_old else "否"
            v_new = "是" if v_new else "否"

        if v_old == v_new or v_old == missing_value:
            continue

        diff_message[label] = [v_old, v_new]

    return diff_message
