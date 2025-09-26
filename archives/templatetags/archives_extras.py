from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(form, field_name):
    """
    Allows accessing a form field with a variable key in templates.
    A Django form can be accessed like a dictionary to get its BoundField.
    Usage: {{ my_form|get_item:my_field_name_string }}
    """
    return form[field_name]

