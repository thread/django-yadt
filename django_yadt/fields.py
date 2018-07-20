import io
import os

from PIL import Image
from django.db import models
from django.db.models import fields
from django.utils.crypto import get_random_string
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.signing import Signer

from .utils import from_dotted_path

IMAGE_VARIANTS = []

class YADTImageField(fields.Field):
    concrete = False

    def __init__(self, variants=None, cachebust=False, track_exists=False, fallback=False, format='jpeg', filename_prefix=lambda x: x.pk, image_class=None):
        super(YADTImageField, self).__init__()

        self.variants = {}
        self.cachebust = cachebust
        self.track_exists = track_exists
        self.filename_prefix = filename_prefix

        self.image_class = image_class or YADTImage

        variants = variants or {}
        for name, config in variants.items():
            if name == 'original':
                raise ValueError("'original' is a reserved variant name")

            if config['format'] not in ('jpeg', 'png'):
                raise ValueError(
                    "'%s' is not a valid format" % config['format']
                )

            self.variants[name] = YADTVariantConfig(
                self,
                name,
                config['format'],
                kwargs=config.get('kwargs', None),
                pipeline=config.get('pipeline', ()),
                fallback=config.get('fallback', False),
            )

        self.variants['original'] = YADTVariantConfig(
            self,
            'original',
            format=format,
            original=True,
            fallback=fallback,
        )

    def get_upload_to(self):
        return os.path.join(
            'yadt',
            '%s.%s' % (
                self.model._meta.app_label,
                self.model._meta.object_name,
            ),
            self.name,
        )

    def contribute_to_class(self, cls, name):
        # Set up this field...
        self.attname = name
        self.name = name
        self.model = cls
        self.column = None

        setattr(cls, name, Descriptor(self, self.image_class))

        cls._meta.add_field(self, private=True)

        # Now set up several other management fields
        self.cachebusting_field = None
        self.exists_field = None

        self.upload_to = self.get_upload_to()

        if self.cachebust:
            self.cachebusting_field = models.CharField(
                max_length=8,
                default='',
                blank=True,
            )

            cls.add_to_class('%s_hash' % name, self.cachebusting_field)

        if self.track_exists:
            self.exists_field = models.BooleanField(default=False)

            cls.add_to_class('%s_exists' % name, self.exists_field)

    def db_type(self, connection):
        return None

class YADTVariantConfig(object):
    def __init__(self, field, name, format, kwargs=None, fallback=None, original=False, pipeline=()):
        self.field = field
        self.name = name

        self.kwargs = kwargs or {}
        self.format = format
        self.fallback = fallback
        self.original = original
        self.pipeline = pipeline

        for x in self.pipeline:
            name = x['name']

            # Allow fields to not require cumbersome prefix in most cases
            if '.' not in name:
                name = 'django_yadt.processors.%s' % x['name']

            x['fn'] = from_dotted_path(name)

        IMAGE_VARIANTS.append(self)

    def fallback_filename(self):
        return os.path.join(
            '%s.%s' % (
                self.field.model._meta.app_label,
                self.field.model._meta.object_name,
            ),
            self.field.name,
            '%s.%s' % (self.name, self.format),
        )

class Descriptor(object):
    def __init__(self, field, image_class):
        self.field = field
        self.image_class = image_class

    def __get__(self, instance=None, owner=None):
        if instance is None:
            return YADTClassImage(self.field)

        return self.image_class(self.field, instance)

##

class YADTImage(object):
    def __init__(self, field, instance, image_file_class=None):
        self.field = field
        self.instance = instance
        self.variants = {}

        image_file_class = image_file_class or YADTImageFile

        for name, config in self.field.variants.items():
            self.variants[name] = image_file_class(
                name,
                config,
                self,
                instance,
            )
        self.__dict__.update(self.variants)

        # Convenience methods
        for x in ('url', 'open'):
            setattr(self, x, getattr(self.original, x))

    def __repr__(self):
        return u"<YADTImage: %s.%s.%s (%s)>" % (
            self.field.model._meta.app_label,
            self.field.model._meta.object_name,
            self.field.name,
            self.field.upload_to,
        )

    def save(self, *args, **kwargs):
        try:
            return self.original.save(*args, **kwargs)
        finally:
            self.mark_exists(True)

    def exists(self):
        if not self.field.exists_field:
            return self.original.exists()

        return getattr(self.instance, self.field.exists_field.name)

    def refresh(self):
        for variant in self.variants.values():
            if not variant.config.original:
                variant.refresh()

    def cachebust(self):
        if self.field.cachebusting_field:
            return setattr(
                self.instance,
                self.field.cachebusting_field.name,
                get_random_string(self.field.cachebusting_field.max_length),
            )

    def mark_exists(self, exists):
        if self.field.exists_field:
            return setattr(self.instance, self.field.exists_field.name, exists)

    def delete(self):
        for variant in self.variants.values():
            variant.delete()
        self.cachebust()
        self.mark_exists(False)

class YADTImageFile(object):
    def __init__(self, name, config, image, instance):
        self.name = name
        self.image = image
        self.config = config
        self.instance = instance

        self.filename = os.path.join(
            self.image.field.upload_to,
            self.name,
            '%s.%s' % (
                self.image.field.filename_prefix(self.instance),
                self.config.format,
            ),
        )

    def __repr__(self):
        return u"<YADTImageFile: %s>" % self.filename

    @property
    def url(self):
        url = default_storage.url(self.filename)

        if self.image.field.cachebusting_field:
            suffix = getattr(
                self.instance,
                self.image.field.cachebusting_field.name,
            )

            if suffix:
                # If URL already has a querystring, append an anonymous param.
                if '?' in url:
                    url += '&_=%s' % suffix
                else:
                    url += '?%s' % suffix

        return url

    def exists(self):
        return default_storage.exists(self.filename)

    def save(self, content):
        self.delete()

        filename = default_storage.save(self.filename, content)

        if filename != self.filename:
            raise RuntimeError(
                "Image was not stored at the location we wanted (%r vs %r)" % (
                    filename,
                    self.filename,
                )
            )

        if self.config.original:
            self.image.refresh()

        self.image.cachebust()

    def open(self, mode='rb'):
        return default_storage.open(self.filename)

    def delete(self):
        return default_storage.delete(self.filename)

    def refresh(self):
        if self.config.original:
            raise NotImplementedError("Cannot refresh the original image")

        im = Image.open(self.image.original.open())

        if im.format == 'PNG':
            original_im = im.copy()
            original_im = original_im.convert('RGBA')
            im = Image.new('RGBA', original_im.size, (255, 255, 255, 255))
            im.paste(original_im, (0, 0), original_im)
        else:
            im = im.convert('RGB')

        # Apply processing pipeline
        for x in self.config.pipeline:
            im = x['fn'](im, x)

        if self.config.format != 'png':
            # Explicitly remove the alpha channel
            im = im.convert('RGB')

        fileobj = io.BytesIO()
        im.save(fileobj, self.config.format, **self.config.kwargs)

        self.save(InMemoryUploadedFile(
            fileobj,
            None,
            self.filename,
            'application/octet-stream',
            len(fileobj.getvalue()),
            None,
        ))

##

class YADTClassImage(object):
    def __init__(self, field):
        self.field = field

        self.variants = {}

        for name, config in self.field.variants.items():
            self.variants[name] = YADTClassVariant(name, config, self)
        self.__dict__.update(self.variants)

    def __repr__(self):
        return u"<YADTClassImage: %s.%s.%s (%s)>" % (
            self.field.model._meta.app_label,
            self.field.model._meta.object_name,
            self.field.name,
            self.field.upload_to,
        )

class YADTClassVariant(object):
    def __init__(self, name, config, image):
        self.name = name
        self.image = image
        self.config = config

    def refresh_all(self, generator=False):
        if self.config.original:
            raise NotImplementedError("Cannot refresh the original image")

        for instance in self.image.field.model._default_manager.order_by():
            image = getattr(instance, self.image.field.name)

            if image.original.exists():
                getattr(image, self.name).refresh()

            yield image

        self.invalidate_all()

    def invalidate_all(self):
        if self.image.field.cachebusting_field:
            field = self.image.field.cachebusting_field

            field.model.objects.update(**{
                field.name: get_random_string(field.max_length)
            })

    def cachebust(self):
        if self.field.cachebusting_field:
            return setattr(
                self.instance,
                self.field.cachebusting_field.name,
                get_random_string(self.field.cachebusting_field.max_length),
            )

class HMACYADTImageField(YADTImageField):
    def __init__(self, salt='django_yadt.fields.HMACYADTImageField', *args, **kwargs):
        kwargs['filename_prefix'] = lambda x: Signer(
            salt=salt,
            sep='_',
        ).sign(x.pk)

        super(HMACYADTImageField, self).__init__(*args, **kwargs)

    def get_upload_to(self):
        return os.path.join(
            'hmacyadt',
            '%s.%s' % (
                self.model._meta.app_label,
                self.model._meta.object_name,
            ),
            self.name,
        )
