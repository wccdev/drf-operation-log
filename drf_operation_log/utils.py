import ast
from collections.abc import MutableMapping

from django.db.models import Manager, Model
from rest_framework.fields import BooleanField, ChoiceField
from rest_framework.serializers import ListSerializer, Serializer

attribute_sep = ">"
missing_value = object()

CLEANED_SUBSTITUTE = "******"
sensitive_fields = {}


def split_get(o: object, concat_attr: str, sep: str = attribute_sep):
    for attr in concat_attr.split(sep):
        try:
            o = getattr(o, attr)
        except AttributeError:
            return missing_value

    return o


def _get_primary_key(serializer: Serializer):
    serializer_meta = getattr(serializer, "Meta", None)
    if not serializer_meta:
        return None
    serializer_meta_model = getattr(serializer_meta, "model", None)
    if not serializer_meta_model:
        return None
    return serializer_meta_model._meta.pk


def _get_source_fields(fields):
    return {f.source: f for f in fields.values() if f.source != "*"}


def _get_many_fields(serializer: Serializer) -> dict:
    many_fields = dict()
    for f in serializer.fields.values():
        if (
            f.source != "*"
            and isinstance(f, ListSerializer)
            and not getattr(f, "read_only", False)
        ):
            # 查找model主键
            primary_key_field = _get_primary_key(f.child)
            child_source_fields = _get_source_fields(f.child.fields)
            if primary_key_field and child_source_fields:
                # 如果serializer中包含当前model的主键字段，才记录
                if primary_key_field.name in child_source_fields:
                    many_fields[f.source] = (
                        child_source_fields,
                        primary_key_field.name,
                        f.label if f.label else f.source,
                    )
    return many_fields


def _flatten_dict_gen(d, parent_key, sep, exclude_fields=None, level=1):
    for k, v in d.items():
        if getattr(v, "read_only", False):
            continue

        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, MutableMapping):
            yield from flatten_dict(v, new_key, sep=sep).items()
        elif isinstance(v, Serializer):
            yield from flatten_dict(
                _get_source_fields(v.fields), new_key, sep=sep, level=level + 1
            ).items()
        # 主表下的子表列表,并且子表数据包含主键，不压平比较
        elif (
            exclude_fields
            and k in exclude_fields
            and isinstance(v, ListSerializer)
            and level == 1
        ):
            continue
        else:
            yield new_key, v


def flatten_dict(
    d: MutableMapping,
    parent_key: str = "",
    sep: str = attribute_sep,
    exclude_fields=None,
    level=1,
):
    return dict(
        _flatten_dict_gen(d, parent_key, sep, exclude_fields=exclude_fields, level=level)
    )


def clean_sensitive_data(data, sensitive_fields=sensitive_fields or {}):
    if isinstance(data, bytes):
        data = data.decode(errors="replace")

    if isinstance(data, list):
        for _l in data:
            clean_sensitive_data(_l)

    if isinstance(data, dict):

        if "changed" in data:
            clean_sensitive_data(data.get("changed"))

        if "added" in data:
            clean_sensitive_data(data.get("added"))

        if "deleted" in data:
            clean_sensitive_data(data.get("deleted"))

        SENSITIVE_FIELDS: set = {
            "api",
            "token",
            "key",
            "secret",
            "password",
            "signature",
        }

        if sensitive_fields:
            SENSITIVE_FIELDS = SENSITIVE_FIELDS | {
                field.lower() for field in sensitive_fields
            }
        if "nested" in data:
            clean_sensitive_data(data.get("nested"))
        elif "field" in data:
            if (
                data.get("field", None) in SENSITIVE_FIELDS
                or data.get("label") in SENSITIVE_FIELDS
            ):
                data.update(
                    {"old_value": CLEANED_SUBSTITUTE, "new_value": CLEANED_SUBSTITUTE}
                )


def serializer_changed_data_diff(
    old_data: dict,
    new_data: dict,
    serializer: Serializer or None,
    trans_dic: dict = None,
) -> dict:
    """
    判断两个个序列化器校验后数据数据差异
    :return:
    """
    if not trans_dic:
        trans_dic = flatten_dict(_get_source_fields(serializer.fields))

    ret = {}
    changed_list = list()

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
            changed_msg = {
                "field": k_new,
                "label": label,
                "old_value": v_old,
                "new_value": v_new,
            }
            clean_sensitive_data(changed_msg)
            changed_list.append(changed_msg)
        except KeyError:
            pass
    if changed_list:
        ret["changed"] = changed_list
    return ret


def serializer_data_diff(serializer: Serializer):
    # 子表字段
    many_fields = _get_many_fields(serializer)
    new_message = flatten_dict(
        serializer.validated_data, exclude_fields=many_fields.keys()
    )

    old_message = {}
    for k in new_message.keys():
        old_message[k] = split_get(serializer.instance, k)
    main_trans_dic = flatten_dict(
        _get_source_fields(serializer.fields), exclude_fields=many_fields.keys()
    )
    main_diff = serializer_changed_data_diff(
        old_message, new_message, serializer, main_trans_dic
    )

    # 比较子表的差异
    if many_fields:
        changed_list = main_diff.get("changed", list())
        # 遍历子表字段 {f.source: (fields, primary_key_name, label)}
        for k, v in many_fields.items():
            child_changed_list = list()
            _child_source_fields, _primary_key_name, _label = v
            # 取出新的子列表数据
            new_k_data_list = serializer.validated_data.get(k)
            if not new_k_data_list:
                continue
            # 取出旧的子列表数据
            old_k_data_list = getattr(serializer.instance, k)
            if not old_k_data_list:
                continue
            else:
                if hasattr(old_k_data_list, "valid") and callable(old_k_data_list.valid):
                    old_k_data_list = old_k_data_list.valid()
                else:
                    old_k_data_list = old_k_data_list.all()
            # 构造旧的子列表【主键->对象】的映射关系
            old_k_data_dict = {getattr(d, _primary_key_name): d for d in old_k_data_list}

            # 遍历新的子列表数据
            for new_d in new_k_data_list:
                # 获取主键的值
                primary_key = new_d.get(_primary_key_name)
                new_d_message = flatten_dict(new_d, level=2)
                new_d_message.pop(_primary_key_name, None)
                # 如果没有主键，认定为新增
                if not primary_key:
                    child_changed_list.append({"added": []})
                else:
                    if isinstance(primary_key, Model):
                        primary_key = primary_key.pk
                    # 取出主键对应的旧值，并从旧列表中移除
                    old_d = old_k_data_dict.pop(primary_key, None)
                    if old_d:
                        old_d_message = {}
                        for d_k in new_d_message.keys():
                            old_d_message[d_k] = split_get(old_d, d_k)
                        trans_dic = flatten_dict(_child_source_fields, level=2)
                        # 比较差异，如果有差异，放入差异列表中
                        child_diff = serializer_changed_data_diff(
                            old_d_message, new_d_message, None, trans_dic
                        )
                        if child_diff:
                            child_changed_list.append(child_diff)

            # 遍历完新的子表数据，仍在旧表中的数据，认定为已从新的数据中删除
            if old_k_data_dict:
                for _, _ in old_k_data_dict.items():
                    child_changed_list.append({"deleted": []})
            # 如果子表数据有变化，记录到总的记录中
            if child_changed_list:
                changed_list.append(
                    {"field": k, "label": _label, "nested": child_changed_list}
                )
        if changed_list:
            main_diff["changed"] = changed_list
    if main_diff:
        return [main_diff]
    else:
        return []


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


def format_excluded_fields(excluded_fields):
    """
    格式化排除字段：
    ["aaa", "bbb"], {"CCC": ["aaa", "bbb"]}
    """
    level_1_field_list = list()
    level_2_field_map = dict()
    for exclude_field in excluded_fields:
        exclude_path = exclude_field.split(".")
        level = len(exclude_path)
        if level == 1:
            level_1_field_list.append(exclude_path[0])
        elif level == 2:
            if exclude_path[0].endswith("[]"):
                level_1_field = exclude_path[0].rstrip("[]")
                level_2_fields = level_2_field_map.get(level_1_field)
                if level_2_fields is None:
                    level_2_fields = list()
                    level_2_field_map[level_1_field] = level_2_fields
                level_2_fields.append(exclude_path[1])
            else:
                level_1_field_list.append(
                    f"{exclude_path[0]}{attribute_sep}{exclude_path[1]}"
                )
    return level_1_field_list, level_2_field_map


def _clean_excluded_fields(data, excluded_fields):
    if data and isinstance(data, list):
        for i in range(len(data) - 1, -1, -1):
            if (
                data[i].get("field") in excluded_fields
                or data[i].get("label") in excluded_fields
            ):
                data.pop(i)


def clean_excluded_fields(
    data, level_1_excluded_fields: list, level_2_excluded_field_map: dict
):
    if isinstance(data, list):
        if level_1_excluded_fields:
            for d in data:
                # 找到主表的变更记录，清理数据
                level_1_changed = d.get("changed")
                if level_1_changed:
                    _clean_excluded_fields(level_1_changed, level_1_excluded_fields)

                    # 如果需要清理子表表更记录
                    if level_2_excluded_field_map:
                        for level_2_d in level_1_changed:
                            level_2_excluded_fields = None
                            if level_2_d.get("field") in level_2_excluded_field_map:
                                level_2_excluded_fields = level_2_excluded_field_map.get(
                                    level_2_d.get("field")
                                )
                            elif level_2_d.get("label") in level_2_excluded_field_map:
                                level_2_excluded_fields = level_2_excluded_field_map.get(
                                    level_2_d.get("label")
                                )
                            if level_2_excluded_fields:
                                nested = level_2_d.get("nested")
                                if nested:
                                    # 查找到子表每一条明细的变更记录，清理数据
                                    for n in nested:
                                        level_2_changed = n.get("changed")
                                        if level_2_changed:
                                            _clean_excluded_fields(
                                                level_2_changed, level_2_excluded_fields
                                            )
