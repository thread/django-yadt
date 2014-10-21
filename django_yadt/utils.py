import os

from django.db import models
from django.core.management.base import CommandError

def get_variant(app_label, model_name, field_name, variant_name):
    model = models.get_model(app_label, model_name)

    if model is None:
        raise CommandError("%s.%s is not a valid model name" % (
            app_label,
            model_name,
        ))

    try:
        field = getattr(model, field_name)
    except AttributeError:
        raise CommandError("%s.%s has no field %s" % (
            app_label,
            model_name,
            field_name,
        ))

    try:
        return getattr(field, variant_name)
    except AttributeError:
        raise CommandError("%s.%s.%s has no variant %s" % (
            app_label,
            model_name,
            field_name,
            variant_name,
        ))

def get_variant_from_path(path):
    # Inline to avoid circular import and to imply that it's late anyway
    from .fields import IMAGE_VARIANTS

    for variant in IMAGE_VARIANTS:
        # Append '' so we don't accidentally match a prefix
        dirname = os.path.join(variant.field.upload_to, variant.name, '')

        if path.startswith(dirname):
            return variant

    return None

def from_dotted_path(fullpath):
    """
    Returns the specified attribute of a module, specified by a string.

    ``from_dotted_path('a.b.c.d')`` is roughly equivalent to::

        from a.b.c import d

    except that ``d`` is returned and not entered into the current namespace.
    """

    module, attr = fullpath.rsplit('.', 1)

    return getattr(
        __import__(module, {}, {}, (attr,)),
        attr,
    )
