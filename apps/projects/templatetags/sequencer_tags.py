from django import template

register = template.Library()

BADGES = {
    "Passed": "text-bg-success",
    "Failed": "text-bg-danger",
    "Warning": "text-bg-warning",
    "Information": "text-bg-secondary",
    "Soft trade-off": "text-bg-info",
    "OPTIMAL": "text-bg-success",
    "FEASIBLE": "text-bg-primary",
    "INFEASIBLE": "text-bg-danger",
    "UNKNOWN": "text-bg-warning",
    "ERROR": "text-bg-danger",
    "INVALID": "text-bg-danger",
    "Not run": "text-bg-secondary",
    "active": "text-bg-success",
    "archived": "text-bg-secondary",
    "hard": "text-bg-danger",
    "soft": "text-bg-info",
    "error": "text-bg-danger",
    "warning": "text-bg-warning",
}


@register.filter(name="attr")
def attribute(attributes, key: str) -> str:
    if not isinstance(attributes, dict):
        return "—"
    value = attributes.get(key)
    if value is None or value == "":
        return "—"
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return str(value)


@register.filter
def badge_class(value) -> str:
    return BADGES.get(str(value), "text-bg-secondary")


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs) -> str:
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"
