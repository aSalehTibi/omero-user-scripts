#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
This produces a report of the raw byte size for each selected image.
"""

import sys
import locale
try:
    locale.setlocale(locale.LC_ALL, 'en_GB')
except:
    pass

import omero
import omero.scripts as scripts
from omero.gateway import BlitzGateway
from omero.rtypes import *  # noqa

PARAM_DATATYPE = "Data_Type"
PARAM_IDS = "IDs"
PARAM_ALL_IMAGES = "All_Images"
PARAM_READABLE = "Readable_Bytes"
PARAM_ARCHIVED = "Include_Archived"

# Global dictionary of original file IDs
original_ids = {}


def bytes_per_pixel(pixel_type):
    """
    Return the number of bytes per pixel for the given pixel type

    @param pixel_type:  The OMERO pixel type
    @type pixel_type:   String
    """
    if (pixel_type == "int8" or pixel_type == "uint8"):
        return 1
    elif (pixel_type == "int16" or pixel_type == "uint16"):
        return 2
    elif (pixel_type == "int32" or
          pixel_type == "uint32" or
          pixel_type == "float"):
        return 4
    elif pixel_type == "double":
        return 8
    else:
        raise Exception("Unknown pixel type: %s" % (pixel_type))


###############################################################################
# Convert bytes into human readable format
def convert_readable(number, verbosity=100, raw_bytes=False):
    """
    Convert bytes into human-readable representation

    @param number:     The number of bytes_per_pixel
    @param verbosity:  The verbosity of the readable format
    @param raw_bytes:  Do not translate to human readable bytes
    """
    if raw_bytes:
        return '%d Byte%s' % (number, number != 1 and 's' or '')
    if number == 0:
        return '0 Bytes'
    negative = ''
    if number < 0:
        negative = '-'
        number = -number
    assert 0 < number < 1 << 110, 'number out of range'
    ordered = reversed(tuple(format_bytes(partition_number(number, 1 << 10))))
    data = []
    count = 0
    for item in ordered:
        if item[0] != '0':
            data.append(item)
            if count >= verbosity:
                break
            count += 1
    cleaned = negative + ', '.join(data)
    return cleaned


def partition_number(number, base):
    """Continually divide number by base until zero."""
    div, mod = divmod(number, base)
    yield mod
    while div:
        div, mod = divmod(div, base)
        yield mod


def format_bytes(parts):
    """Format partitioned bytes into human-readable strings."""
    for power, number in enumerate(parts):
        yield "%s %s" % (number, format_suffix(power, number))


def format_suffix(power, number):
    """Compute the suffix for a certain power of bytes."""
    result = (PREFIX[power] + 'byte').capitalize()
    if number != 1:
        result += 's'
    return result

PREFIX = ' kilo mega giga tera peta exa zetta yotta bronto geop'.split(' ')

###############################################################################


def convert_raw(number, verbosity=100):
    """Convert bytes into a string."""
    return '%s Byte%s' % (locale.format('%d', number, True),
                          number != 1 and 's' or '')


def process_image(conn, img, params):
    """
    Calculate the raw byte size

    @param conn:   The BlitzGateway connection
    @param img:    The ImageWrapper object
    @param params: The script parameters
    """
    (x, y, c, z, t) = (img.getSizeX(), img.getSizeY(), img.getSizeC(),
                       img.getSizeZ(), img.getSizeT())
    bytes = x * y * c * z * t * bytes_per_pixel(img.getPixelsType())
    ds = img.getParent()
    if ds:
        pr = ds.getParent()
    else:
        pr = None

    msg = "Image %d : [%s][%s] %s : %s" % (
          img.getId(),
          pr and pr.getName() or '-',
          ds and ds.getName() or '-',
          img.getName(),
          convert(bytes))

    archive_bytes = 0
    if params[PARAM_ARCHIVED] and img.getArchived():
        pids = rlist(rlong(img.getPixelsId()))
        param = omero.sys.ParametersI()
        param.add("pids", pids)
        results = conn.getQueryService().findAllByQuery(
            "select m from PixelsOriginalFileMap as m join fetch m.parent "
            "where m.child.id=:pids", param)

        origFile = None
        for result in results:
            origFile = result.parent
            # oid = result.details.owner.id.val
            p_size = origFile.size.val
            archive_bytes += p_size

        if origFile:
            msg += " : Archive ID [%d] %s" % (
                origFile.id.val, convert(archive_bytes))

            # Original files can contain multiple images so only count
            # archived bytes in total once
            if origFile.id.val in original_ids:
                archive_bytes = 0
            else:
                original_ids[origFile.id.val] = True
        else:
            msg += " : Archive unknown"

    print msg

    return (bytes, archive_bytes)


def run(conn, params):
    """
    For each image defined in the script parameters calculate the raw byte size

    @param conn:   The BlitzGateway connection
    @param params: The script parameters
    """
    # print "Parameters = %s" % params

    # Create the global conversion function for text byte output
    global convert
    if params.get(PARAM_READABLE):
        convert = convert_readable
    else:
        convert = convert_raw

    images = []
    if params.get(PARAM_ALL_IMAGES):
        images = list(conn.getObjects('Image'))
    else:
        objects = conn.getObjects(params[PARAM_DATATYPE],
                                  params.get(PARAM_IDS, [0]))
        if params[PARAM_DATATYPE] == 'Dataset':
            for ds in objects:
                images.extend(list(ds.listChildren()))
        else:
            images = list(objects)

        # Remove duplicate images in multiple datasets
        seen = set()
        images = [x for x in images if x.id not in seen and not seen.add(x.id)]

    print("Processing %s image%s" % (
        len(images), len(images) != 1 and 's' or ''))

    print "-=-=-=-"

    count = 0
    total = 0L
    total_archived = 0L
    for img in images:
        if (img is not None):
            (bytes, archived_bytes) = process_image(conn, img, params)
            if bytes > 0:
                count += 1
                total += bytes
                total_archived += archived_bytes

    if count:
        print "-=-=-=-"

    return (count, total, total_archived)


def summary(count, total, total_archived):
    """Produce a summary message of the image count and total byte size"""
    msg = "%d image%s : %s" % (count, count != 1 and 's' or '',
                               convert(total))
    if total_archived:
        msg += " : Archived %s" % convert(total_archived)
    return msg


def run_as_program():
    """
    Testing function to allow the script to be called outside of the OMERO
    scripting environment. The connection details and image ID must be valid.
    """
    import getpass
    HOST = 'localhost'
    PORT = 4064
    USERNAME = raw_input("OMERO username: ")
    PASSWORD = getpass.getpass("OMERO password: ")
    h = raw_input("OMERO host (%s): " % HOST)
    if h:
        HOST = h
    p = raw_input("OMERO port (%d): " % PORT)
    if p:
        PORT = p

    conn = BlitzGateway(USERNAME, PASSWORD, host=HOST, port=PORT)
    conn.connect()

    params = {}
    params[PARAM_IDS] = [51, 161]
    params[PARAM_DATATYPE] = "Image"
    params[PARAM_ARCHIVED] = True
    params[PARAM_READABLE] = True

    global raw_bytes
    raw_bytes = False

    (count, total, total_archived) = run(conn, params)

    print (summary(count, total, total_archived))


def run_as_script():
    """
    The main entry point of the script, as called by the client via the
    scripting service, passing the required parameters.
    """
    dataTypes = [rstring('Dataset'), rstring('Image')]

    client = scripts.client('Image_Size.py', """\
Report the raw byte size of each image.

    size = W x H x C x Z x T x [bytes per pixel]

Optionally includes the original file size (if archived during import).

See: http://www.sussex.ac.uk/gdsc/intranet/microscopy/omero/scripts/imagesize""",  # noqa

    scripts.String(PARAM_DATATYPE, optional=False, grouping="1.1",
        description="The data you want to work with.", values=dataTypes,
        default="Image"),

    scripts.List(PARAM_IDS, optional=True, grouping="1.2",
        description="List of Dataset IDs or Image IDs").ofType(rlong(0)),

    scripts.Bool(PARAM_ALL_IMAGES, grouping="1.3",
        description="Process all images (ignore the ID parameters)",
        default=False),

    scripts.Bool(PARAM_READABLE, grouping="4",
        description="Show human-readable bytes",
        default=True),

    scripts.Bool(PARAM_ARCHIVED, grouping="5",
        description="Include archived files",
        default=True),

    version="1.0",
    authors=["Alex Herbert", "GDSC"],
    institutions=["University of Sussex"],
    contact="a.herbert@sussex.ac.uk",
    )  # noqa

    try:
        conn = BlitzGateway(client_obj=client)

        # Process the list of args above.
        params = {}
        for key in client.getInputKeys():
            if client.getInput(key):
                params[key] = client.getInput(key, unwrap=True)

        # Call the main script - returns the number of images and total bytes
        (count, total, total_archived) = run(conn, params)

        if count >= 0:
            print "Images : %s" % count
            print "Raw pixels : %s" % convert(total)
            print "Archived : %s" % convert(total_archived)
            print "-=-=-=-"

            # Combine the totals for the summary message
            msg = summary(count, total + total_archived, 0)
            print msg
            client.setOutput("Message", rstring(msg))
    finally:
        client.closeSession()

if __name__ == "__main__":
    """
    Python entry point
    """
    function_to_run = run_as_script

    # Allow the script to be run on the command-line by passing the param 'run'
    for arg in sys.argv:
        if arg == 'run':
            function_to_run = run_as_program

    function_to_run()
