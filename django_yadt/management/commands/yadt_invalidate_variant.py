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

        variant.invalidate_all()
