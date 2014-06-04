# -*- coding: utf-8 -*-
"""
This script gets all the Rectangles from a particular image, then creates new
images with the regions within the ROIs, and saves them back to the server.

This script is adapted from [SCRIPTS]/omero/util_scripts/Images_From_ROIs.py

The script has been modified to allow cropping through the entire T or Z stack
using an ROI defined on a single image plane.
"""

import os
import time

import omero
import omero.scripts as scripts
from omero.gateway import BlitzGateway
from omero.rtypes import *  # noqa

startTime = 0


def splitext(filename):
    """
    Splits a filename into base and extension.
    Handles .ome.tiff as an extension.
    """
    (base, ext) = os.path.splitext(filename)
    # Special case if a .ome.tif since only the .tif will be removed
    if base.endswith('.ome'):
        base = base.replace('.ome', '')
        ext = '.ome' + ext
    return (base, ext)


def createImageName(name, index):
    """
    Adds an ROI-index suffix to the source image names
    """
    name = os.path.basename(name)
    (base, ext) = splitext(name)
    return "%s_roi%d%s" % (base, index, ext)


def printDuration(output=True):
    global startTime
    if startTime == 0:
        startTime = time.time()
    if output:
        print "Script timer = %s secs" % (time.time() - startTime)


def getRectangles(conn, imageId):
    """
    Returns a list of (x, y, width, height, zStart, zStop, tStart, tStop) of
    each rectangle ROI in the image
    """

    rois = []

    roiService = conn.getRoiService()
    result = roiService.findByImage(imageId, None)

    for roi in result.rois:
        zStart = None
        zEnd = 0
        tStart = None
        tEnd = 0
        x = None
        for shape in roi.copyShapes():
            if type(shape) == omero.model.RectI:
                # check t range and z range for every rectangle
                t = shape.getTheT().getValue()
                z = shape.getTheZ().getValue()
                if tStart is None:
                    tStart = t
                if zStart is None:
                    zStart = z
                tStart = min(t, tStart)
                tEnd = max(t, tEnd)
                zStart = min(z, zStart)
                zEnd = max(z, zEnd)
                if x is None:   # get x, y, width, height for first rect only
                    x = int(shape.getX().getValue())
                    y = int(shape.getY().getValue())
                    width = int(shape.getWidth().getValue())
                    height = int(shape.getHeight().getValue())

        # if we have found any rectangles at all...
        if zStart is not None:
            rois.append((x, y, width, height, zStart, zEnd, tStart, tEnd))

    return rois


def processImage(conn, imageId, parameterMap):
    """
    Process an image.
    If imageStack is True, we make a Z-stack using one tile from each ROI (c=0)
    Otherwise, we create a 5D image representing the ROI "cropping" the
    original image. Image is put in a dataset if specified.
    """

    createDataset = parameterMap['New_Dataset']
    datasetName = parameterMap['New_Dataset_Name']

    image = conn.getObject("Image", imageId)
    if image is None:
        return

    parentDataset = image.getParent()
    parentProject = parentDataset.getParent()

    dataset = None
    if not createDataset:
        dataset = parentDataset

    imageName = image.getName()
    updateService = conn.getUpdateService()

    pixels = image.getPrimaryPixels()
    W = image.getSizeX()
    H = image.getSizeY()

    # note pixel sizes (if available) to set for the new images
    physicalSizeX = pixels.getPhysicalSizeX()
    physicalSizeY = pixels.getPhysicalSizeY()
    physicalSizeZ = pixels.getPhysicalSizeZ()

    # Store original channel details
    cNames = []
    emWaves = []
    exWaves = []
    for index, c in enumerate(image.getChannels()):
        lc = c.getLogicalChannel()
        cNames.append(str(c.getLabel()))
        emWaves.append(lc.getEmissionWave())
        exWaves.append(lc.getExcitationWave())

    # x, y, w, h, zStart, zEnd, tStart, tEnd
    rois = getRectangles(conn, imageId)
    print "rois"
    print rois

    # Make a new 5D image per ROI
    iIds = []
    for index, r in enumerate(rois):
        x, y, w, h, z1, z2, t1, t2 = r
        # Bounding box
        if x < 0:
            x = 0
        if y < 0:
            y = 0
        if x + w > W:
            w = W - x
        if y + h > H:
            h = H - y

        if parameterMap['Entire_Stack']:
            if parameterMap['Z_Stack']:
                z1 = 0
                z2 = image.getSizeZ() - 1
            if parameterMap['T_Stack']:
                t1 = 0
                t2 = image.getSizeT() - 1

        print "  ROI x: %s y: %s w: %s h: %s z1: %s z2: %s t1: %s t2: %s" % (
            x, y, w, h, z1, z2, t1, t2)

        # need a tile generator to get all the planes within the ROI
        sizeZ = z2-z1 + 1
        sizeT = t2-t1 + 1
        sizeC = image.getSizeC()
        zctTileList = []
        tile = (x, y, w, h)
        print "zctTileList..."
        for z in range(z1, z2+1):
            for c in range(sizeC):
                for t in range(t1, t2+1):
                    zctTileList.append((z, c, t, tile))

        def tileGen():
            for i, t in enumerate(pixels.getTiles(zctTileList)):
                yield t

        print "sizeZ, sizeC, sizeT", sizeZ, sizeC, sizeT
        description = """\
Created from Image ID: %d
  Name: %s
  x: %d y: %d w: %d h: %d""" % (imageId, imageName, x, y, w, h)
        # make sure that script_utils creates a NEW rawPixelsStore
        serviceFactory = conn.c.sf  # noqa
        newI = conn.createImageFromNumpySeq(
            tileGen(), createImageName(imageName, index),
            sizeZ=sizeZ, sizeC=sizeC, sizeT=sizeT, description=description,
            dataset=dataset)
        iIds.append(newI.getId())

        # Apply colors from the original image to the new one
        if newI._prepareRenderingEngine():
            renderingEngine = newI._re

            # Apply the original channel names
            newPixels = renderingEngine.getPixels()

            for i, c in enumerate(newPixels.iterateChannels()):
                lc = c.getLogicalChannel()
                lc.setEmissionWave(rint(emWaves[i]))
                lc.setExcitationWave(rint(exWaves[i]))
                lc.setName(rstring(cNames[i]))
                updateService.saveObject(lc)

            renderingEngine.resetDefaults()

        # Apply the original pixel size - Get the object again to refresh state
        newImg = conn.getObject("Image", newI.getId())
        newPixels = newImg.getPrimaryPixels()
        newPixels.setPhysicalSizeX(rdouble(physicalSizeX))
        newPixels.setPhysicalSizeY(rdouble(physicalSizeY))
        newPixels.setPhysicalSizeZ(rdouble(physicalSizeZ))
        newPixels.save()

    if len(iIds) > 0 and createDataset:

        # create a new dataset for new images
        print "\nMaking Dataset '%s' of Images from ROIs of Image: %s" % (
            datasetName, imageId)
        dataset = omero.model.DatasetI()
        dataset.name = rstring(datasetName)
        desc = """\
Images in this Dataset are from ROIs of parent Image:
Name: %s
Image ID: %d""" % (imageName, imageId)
        dataset.description = rstring(desc)
        dataset = updateService.saveAndReturnObject(dataset)
        for iid in iIds:
            link = omero.model.DatasetImageLinkI()
            link.parent = omero.model.DatasetI(dataset.id.val, False)
            link.child = omero.model.ImageI(iid, False)
            updateService.saveObject(link)
        if parentProject:        # and put it in the current project
            link = omero.model.ProjectDatasetLinkI()
            link.parent = omero.model.ProjectI(parentProject.getId(), False)
            link.child = omero.model.DatasetI(dataset.id.val, False)
            updateService.saveAndReturnObject(link)

    return len(iIds)


def makeImagesFromRois(conn, parameterMap):
    """
    Processes the list of Image_IDs, either making a new image-stack or a new
    dataset from each image, with new image planes coming from the regions in
    Rectangular ROIs on the parent images.
    """

    dataType = parameterMap["Data_Type"]
    ids = parameterMap["IDs"]

    count = 0
    if dataType == 'Image':
        for iId in ids:
            count += processImage(conn, iId, parameterMap)
    else:
        for dsId in ids:
            ds = conn.getObject("Dataset", dsId)
            for i in ds.listChildren():
                count += processImage(conn, i.getId(), parameterMap)

    plural = (count == 1) and "." or "s."
    message = "Created %s new image%s" % (count, plural)
    if count > 0:
        message += " Refresh Project to view"
    return message


def runAsScript():
    """
    The main entry point of the script, as called by the client via the
    scripting service, passing the required parameters.
    """
    printDuration(False)    # start timer
    dataTypes = [rstring('Dataset'), rstring('Image')]

    client = scripts.client('New_Images_From_ROIs.py',
"""Create new Images from the regions defined by Rectangle ROIs.
Designed to work with multi-plane images with multiple ROIs per image.
ROIs can span part of the z-stack.

See: http://www.sussex.ac.uk/gdsc/intranet/microscopy/omero/scripts/rois""",

    scripts.String("Data_Type", optional=False, grouping="1",
        description="Choose Images via their 'Dataset' or directly by "
                    "'Image' IDs.",
        values=dataTypes, default="Image"),

    scripts.List("IDs", optional=False, grouping="2",
        description="List of Dataset IDs or Image IDs to process."
        ).ofType(rlong(0)),

    scripts.Bool("Entire_Stack", grouping="3",
        description="Extend each ROI through the entire stack (Z & T planes)",
        default=False),

    scripts.Bool("Z_Stack", grouping="3.1",
        description="Extend each ROI through the entire Z-stack",
        default=True),
    scripts.Bool("T_Stack", grouping="3.2",
        description="Extend each ROI through the entire T-stack",
        default=True),

    scripts.Bool("New_Dataset", grouping="4",
        description="Create images in a new Dataset", default=False),
    scripts.String("New_Dataset_Name", grouping="4.1",
        description="New Dataset name", default="From_ROIs"),

    version="1.0",
    authors=["Alex Herbert"],
    institutions=["GDSC, University of Sussex"],
    contact="a.herbert@sussex.ac.uk",
    )  # noqa

    try:
        # process the list of args above.
        parameterMap = {}
        for key in client.getInputKeys():
            if client.getInput(key):
                parameterMap[key] = client.getInput(key, unwrap=True)

        print parameterMap

        # create a wrapper so we can use the Blitz Gateway.
        conn = BlitzGateway(client_obj=client)

        message = makeImagesFromRois(conn, parameterMap)

        if message:
            client.setOutput("Message", rstring(message))
        else:
            client.setOutput("Message",
                             rstring("Script Failed. See 'error' or 'info'"))

    finally:
        client.closeSession()
        printDuration()

if __name__ == "__main__":
    runAsScript()
