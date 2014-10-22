import Image
import ImageDraw

def crop(im, config):
    """
    Resize and crop to the specified dimensions, regardless of source size.
    """

    src_width, src_height = im.size

    src_ratio = float(src_width) / float(src_height)
    dst_ratio = float(config['width']) / float(config['height'])

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
        y_offset + int(crop_height),
    ))

    return im.resize(
        (config['width'], config['height']),
        Image.ANTIALIAS,
    )

def thumbnail(im, config):
    """
    Create a thumbnail "no larger than the given size", ie. without upsizing.
    """

    im.thumbnail(
        (config['width'], config['height']),
        Image.ANTIALIAS,
    )

    return im

def circle(im, config):
    """
    Apply a circular mask to emulate "border-radius: 50%;" in CSS.
    """

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

    return im
