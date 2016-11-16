import sys

from django.core.management.base import BaseCommand, CommandError

from ...utils import get_variant


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('app_label')
        parser.add_argument('model_name')
        parser.add_argument('field_name')
        parser.add_argument('variant_name')

    def handle(self, *args, **options):
        variant = get_variant(
            options['app_label'],
            options['model_name'],
            options['field_name'],
            options['variant_name'],
        )

        for x in variant.refresh_all(generator=True):
            sys.stderr.write('.')
        sys.stderr.write('\n')
