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
