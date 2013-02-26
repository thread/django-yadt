import os

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from ...utils import get_variant

class Command(BaseCommand):
    USAGE = "<app_label> <model> <field> <variant>"

    def handle(self, *args, **options):
        try:
            app_label, model_name, field_name, variant_name = args
        except ValueError:
            raise CommandError(self.USAGE)

        variant = get_variant(app_label, model_name, field_name, variant_name)

        in_database = set(
            getattr(getattr(x, field_name), variant_name).filename
            for x in variant.image.field.model._default_manager.all()
        )

        base = os.path.join(
            variant.image.field.upload_to,
            variant.name,
        )

        on_disk = set(
            os.path.join(
                variant.image.field.upload_to,
                variant.name,
                x,
            ) for x in os.listdir(default_storage.path(base))
        )

        for x in on_disk.difference(in_database):
            print "I: Can be deleted: %s" % x
