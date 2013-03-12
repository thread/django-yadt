import os
import optparse

from django.core.management.base import NoArgsCommand

from ...fields import IMAGE_VARIANTS

TEMPLATE = """
location ~ ^%(source_prefix)s%(source)s/ {
  error_page 404 = "%(target_prefix)s%(target)s";
}
"""

class Command(NoArgsCommand):
    option_list = NoArgsCommand.option_list + (
        optparse.make_option(
            '--source-prefix',
            dest='source_prefix',
            help="Where storage media is served from",
            default='',
        ),
        optparse.make_option(
            '--target-prefix',
            dest='target_prefix',
            help="Where fallback images are served from",
            default='/',
        ),
    )

    def handle_noargs(self, **options):
        for variant in IMAGE_VARIANTS:
            self.handle_variant(variant, options)

    def handle_variant(self, variant, options):
        if not variant.fallback:
            return

        print TEMPLATE.strip() % dict(
            source=os.path.join(variant.field.upload_to, variant.name),
            target=variant.fallback_filename(),
            **options
        )
