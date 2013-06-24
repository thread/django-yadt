import os
import Image
import StringIO
import ImageDraw

from django.db import models
from django.utils.crypto import get_random_string
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import InMemoryUploadedFile

IMAGE_VARIANTS = []

class YADTImageField(object):
    def __init__(self, variants=None, cachebust=False, fallback=False, format='jpeg'):
        self.variants = {}
        self.cachebust = cachebust

        variants = variants or {}
        for name, config in variants.iteritems():
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
                crop=config.get('crop', False),
                width=config.get('width', None),
                height=config.get('height', None),
                fallback=config.get('fallback', False),
                transform=config.get('transform', None),
            )

        self.variants['original'] = YADTVariantConfig(
            self,
            'original',
            format=format,
            original=True,
            fallback=fallback,
        )

    def contribute_to_class(self, cls, name):
        self.model = cls
        self.name = name
        self.cachebusting_field = None

        self.upload_to = os.path.join(
            'yadt',
            '%s.%s' % (
                self.model._meta.app_label,
                self.model._meta.object_name,
            ),
            self.name,
        )

        if self.cachebust:
            self.cachebusting_field = models.CharField(
                max_length=8,
                default='',
                blank=True,
            )

            cls.add_to_class(
                '%s_hash' % name,
                self.cachebusting_field,
            )

        cls._meta.add_virtual_field(self)

        setattr(cls, name, Descriptor(self))

class YADTVariantConfig(object):
    def __init__(self, field, name, format, width=None, height=None, crop=False, fallback=None, transform=None, original=False):
        self.field = field
        self.name = name

        self.crop = crop
        self.width = width
        self.height = height
        self.format = format
        self.transform = transform
        self.fallback = fallback

        self.original = original

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
    def __init__(self, field):
        self.field = field

    def __get__(self, instance=None, owner=None):
        if instance is None:
            return YADTClassImage(self.field)

        return YADTImage(self.field, instance)

##

class YADTImage(object):
    def __init__(self, field, instance):
        self.field = field
        self.instance = instance
        self.variants = {}

        for name, config in self.field.variants.iteritems():
            self.variants[name] = YADTImageFile(name, config, self, instance)
        self.__dict__.update(self.variants)

        # Convenience methods
        for x in ('url', 'save', 'open', 'exists'):
            setattr(self, x, getattr(self.original, x))

    def __repr__(self):
        return u"<YADTImage: %s.%s.%s (%s)>" % (
            self.field.model._meta.app_label,
            self.field.model._meta.object_name,
            self.field.name,
            self.field.upload_to,
        )

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

class YADTImageFile(object):
    def __init__(self, name, config, image, instance):
        self.name = name
        self.image = image
        self.config = config
        self.instance = instance

        self.filename = os.path.join(
            self.image.field.upload_to,
            self.name,
            '%d.%s' % (self.instance.pk, self.config.format),
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
                url += '?%s' % suffix

        return url

    def exists(self):
        return default_storage.exists(self.filename)

    def save(self, content):
        default_storage.delete(self.filename)

        filename = default_storage.save(self.filename, content)

        assert filename == self.filename, "Image was not stored at the " \
            "location we wanted (%r vs %r)" % (filename, self.filename)

        if self.config.original:
            self.image.refresh()

        self.image.cachebust()

    def open(self, mode='rb'):
        return default_storage.open(self.filename)

    def refresh(self):
        if self.config.original:
            raise NotImplementedError("Cannot refresh the original image")

        im = Image.open(self.image.original.open())

        im = im.convert('RGB')

        if self.config.width and self.config.height:
            if self.config.crop:
                src_width, src_height = im.size

                src_ratio = float(src_width) / float(src_height)
                dst_ratio = float(self.config.width) / float(self.config.height)

                if dst_ratio < src_ratio:
                    crop_height = src_height
                    crop_width = crop_height * dst_ratio
                    x_offset = int(float(src_width - crop_width) / 2)
                    y_offset = 0
                else:
                    crop_width = src_width
                    crop_height = crop_width / dst_ratio
                    x_offset = 0
                    y_offset = int(float(src_height - crop_height) / 3)

                im = im.crop((
                    x_offset,
                    y_offset,
                    x_offset + int(crop_width),
                    y_offset + int(crop_height))
                )

                im = im.resize(
                    (self.config.width, self.config.height),
                    Image.ANTIALIAS,
                )
            else:
                im.thumbnail(
                    (self.config.width, self.config.height),
                    Image.ANTIALIAS,
                )

            if self.config.transform == 'circle':
                # Supersample the mask to avoid aliasing
                mask_size = (im.size[0] * 10, im.size[1] * 10)

                # Create circular mask
                mask = Image.new('L', mask_size, 0)
                ImageDraw.Draw(mask).ellipse((0, 0) + mask_size, fill=255)
                mask.thumbnail(im.size, Image.ANTIALIAS)

                # Need a new white background to paste it on
                existing = im
                existing.putalpha(mask)
                im = Image.new('RGBA', existing.size, (255, 255, 255, 0))
                im.paste(existing, mask=existing.split()[3])

        fileobj = StringIO.StringIO()
        im.save(fileobj, self.config.format)

        self.save(InMemoryUploadedFile(
            fileobj,
            None,
            self.filename,
            'application/octet-stream',
            fileobj.len,
            None,
        ))

##

class YADTClassImage(object):
    def __init__(self, field):
        self.field = field

        self.variants = {}

        for name, config in self.field.variants.iteritems():
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

        for instance in self.image.field.model.objects.all():
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

