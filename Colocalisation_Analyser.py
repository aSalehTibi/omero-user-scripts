#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
This script runs the ImageJ GDSC Stack Colocalisation Analyser plugin.
"""

import os
import sys
import subprocess
import time
import copy
import stat
import re
import tempfile
import platform
import glob
import smtplib
from email.MIMEMultipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email.MIMEText import MIMEText
from email import Encoders
from email.Utils import formatdate

import omero
import omero.scripts as scripts
from omero.gateway import BlitzGateway
from omero.rtypes import *

################################################################################
# CONFIGURATION
################################################################################

# The ImageJ classpath must contain the headless.jar before the ij.jar.
# The headless.jar with source code is available in the GitHub repository 
# containing all the GDSC OMERO scripts.
IMAGEJ_CLASSPATH = "/usr/local/ImageJ/headless.jar:/usr/local/ImageJ/ij.jar"

# The location of the ImageJ install (v1.45+). The [ImageJ]/plugins directory 
# must contain the gdsc_.jar ImageJ plugin:
# http://www.sussex.ac.uk/gdsc/intranet/microscopy/imagej/gdsc_plugins
IMAGEJ_PATH = "/usr/local/ImageJ"

# The e-mail address that messages are sent from. Make this a valid 
# address so that the user can reply to the message.
ADMIN_EMAIL = 'admin@omero.host.com'

################################################################################

PARAM_DATATYPE = "Data_Type"
PARAM_IDS = "IDs"
PARAM_CHANNEL1 = "Channel 1"
PARAM_CHANNEL2 = "Channel 2"
PARAM_CHANNEL3 = "Channel 3"
PARAM_METHOD = "Method"
PARAM_PERMUTATIONS = "Permutations"
PARAM_MIN_SHIFT = "Minimum shift"
PARAM_MAX_SHIFT = "Maximum shift"
PARAM_SIGNIFICANCE = "Significance"
PARAM_UPLOAD_RESULTS = "Upload results"
PARAM_EMAIL_RESULTS = "Email results"
PARAM_EMAIL = "Email"

def build_parameters(params): 
    """Build the parameters used for the analysis"""
    parameters = []
    parameters.append("%s : %s" % ("Channel 1    ", params[PARAM_CHANNEL1]))
    parameters.append("%s : %s" % ("Channel 2    ", params[PARAM_CHANNEL2]))
    parameters.append("%s : %s" % ("Channel 3    ", params[PARAM_CHANNEL3]))
    parameters.append("%s : %s" % ("Method       ", params[PARAM_METHOD]))
    parameters.append("%s : %s" % ("Permutations ", params[PARAM_PERMUTATIONS]))
    parameters.append("%s : %s" % ("Minimum shift", params[PARAM_MIN_SHIFT]))
    parameters.append("%s : %s" % ("Maximum shift", params[PARAM_MAX_SHIFT]))
    parameters.append("%s : %g" % ("Significance ", params[PARAM_SIGNIFICANCE]))
    return parameters
    
def list_image_names(conn, results):
    """Builds a list of the image names"""
    image_names = []
    for image_id, result in results.iteritems():
        img = conn.getObject('Image', image_id)
        if not img:
            continue

        ds = img.getParent()
        if ds:
            pr = ds.getParent()
        else:
            pr = None
            
        image_names.append("[%s][%s] Image %d : %s" % (
                pr and pr.getName() or '-',
                ds and ds.getName() or '-',
                image_id, os.path.basename(img.getName())))

    return image_names

def create_report(conn, results, params):
    """
    Creates a report for the results.
    
    @param conn:    The BlitzGateway connection
    @param results: Dict of (imageId,text_result) pairs
    @param params:  The script parameters
    """
    report = ["Project,Dataset,Image ID,Name,p,Method,Frame,Ch1,Ch2,Ch3,n,Area,M1,Sig,M2,Sig,R,Sig"]
    for image_id, result in results.iteritems():
        img = conn.getObject('Image', image_id)
        if not img:
            continue

        ds = img.getParent()
        if ds:
            pr = ds.getParent()
        else:
            pr = None
            
        lines = result.splitlines()
        for line in lines[1:]: # Ignore first line
            report.append("%s,%s,%d,%s,%s" % (
                pr and pr.getName() or '-',
                ds and ds.getName() or '-',
                image_id, os.path.basename(img.getName()), line))

    return report

def email_results(conn, results, report, params):
    """
    E-mail the result to the user.
    
    @param conn:    The BlitzGateway connection
    @param results: Dict of (imageId,text_result) pairs
    @param report:  The results report
    @param params:  The script parameters
    """
    if not params[PARAM_EMAIL_RESULTS]:
        return

    attach_text = "\n".join(report)

    image_names = list_image_names(conn, results)
    parameters = build_parameters(params)

    msg = MIMEMultipart()
    msg['From'] = ADMIN_EMAIL
    msg['To'] = params[PARAM_EMAIL]
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = '[OMERO Job] Colocalisation analysis'
    msg.attach(MIMEText("""Colocalisation analysis performed on:

%s

Parameters: 

%s

Your analysis results are attached.

---
OMERO @ %s """ % ("\n".join(image_names), "\n".join(parameters), 
    platform.node()) ))

    if attach_text:
        part = MIMEBase('text', "csv")
        part.set_payload(attach_text)
        Encoders.encode_base64(part)
        part.add_header('Content-Disposition', 
                        'attachment; filename="results.csv"')
        msg.attach(part)

    smtpObj = smtplib.SMTP('localhost')
    smtpObj.sendmail(ADMIN_EMAIL, [params[PARAM_EMAIL]], msg.as_string())   
    smtpObj.quit()    

def create_result_name(params):
    """Create the correlation result filename"""
    name = ['Colocalisation', params[PARAM_METHOD]]
    name.append('Ch%s' % params[PARAM_CHANNEL1])
    name.append('Ch%s' % params[PARAM_CHANNEL2])
    if params[PARAM_CHANNEL3]:
        name.append('Ch%s' % params[PARAM_CHANNEL3])
    return '_'.join(name) + '.csv'
    
def upload_results(conn, results, params):
    """
    Uploads the results to each image as an annotation
    
    @param conn:         The BlitzGateway connection
    @param results:      Dict of (imageId,text_result) pairs
    @parms params:       The script parameters
    """
    global tmp_dir
    
    if not params[PARAM_UPLOAD_RESULTS]:
        return
        
    result_name = create_result_name(params)
    
    for image_id, result in results.iteritems():
        img = conn.getObject('Image', image_id)
        if not img:
            continue
        
        (fd, tmp_file) = tempfile.mkstemp(dir=tmp_dir, text=True)
        file = os.fdopen(fd, 'w')
        file.write(result)
        file.close()
        
        name = "%d.%s" % (image_id, result_name)
        ann = conn.createFileAnnfromLocalFile(tmp_file,
            origFilePathAndName=name,
            ns='gdsc.sussex.ac.uk/colocalisation')
        ann = img.linkAnnotation(ann)
        
        os.remove(tmp_file)

def extract_results(result_file):
    """
    Extracts the results from the ImageJ stdout into a dictionary of 
    (imageId,text_result) pairs
    """
    results = dict()
    
    file = open(result_file, 'r')
    
    # Extract results in blocks from the following format:
    #Stack colocalisation (Otsu) : 1851.ome.tif
    #Image,p,Method,Frame,Ch1,Ch2,Ch3,n,Area,M1,Sig,M2,Sig,R,Sig
    #3.tif,0.0500,Otsu,1,c1,c2,None,6528,9.96%,0.9460,true,0.9334,true,0.2940,false
    #3.tif,0.0500,Otsu,2,c1,c2,None,6374,9.73%,0.9232,true,0.9390,true,0.1977,false

    extract_result = False
    image_id = 0
    result = []
    for line in file:
        # Check if currently within an image result
        if extract_result:
            m = re.match("(\d+).ome.tif,(.*)", line)
            if m:
                image_id = long(m.group(1))
                result.append(m.group(2))
            else:
                results[image_id] = "\n".join(result)
                image_id = 0
                extract_result = False
                
        if not extract_result:
            # Look for a new result
            m = re.match("Image,(p,Method.*)", line) 
            if m:
                extract_result = True
                result = [m.group(1)]
    
    if image_id:
        results[image_id] = "\n".join(result)
    
    file.close()
    
    return results    

def run_imagej(conn, images, image_names, params):
    """
    Runs the ImageJ correlation analyser plugin.
    
    @param conn:         The BlitzGateway connection
    @param images:       The list of images
    @param image_names:  List of OME-TIFF image files
    @parms params:       The script parameters
    """
    global tmp_dir
    
    results = {}
    if not image_names:
        return results
    
    # Create a macro for ImageJ
    args = [ "log_results" ]
    args.append("method=%s" % params[PARAM_METHOD] )
    args.append("permutations=%s" % params[PARAM_PERMUTATIONS] )
    args.append("minimum_shift=%s" % params[PARAM_MIN_SHIFT] )
    args.append("maximum_shift=%s" % params[PARAM_MAX_SHIFT] )
    args.append("significance=%s" % params[PARAM_SIGNIFICANCE] )
    args = ' '.join(args)

    macro_file = os.path.join(tmp_dir, "colocalisation.ijm")
    result_file = os.path.join(tmp_dir, "colocalisation.stdout")
    
    out = open(macro_file, 'wb')
    c3 = -1
    for i, name in enumerate(image_names):
        img = images[i]
        
        c1 = find_channel_index(img, params[PARAM_CHANNEL1])
        c2 = find_channel_index(img, params[PARAM_CHANNEL2])
        if params[PARAM_CHANNEL3]:
            c3 = find_channel_index(img, params[PARAM_CHANNEL3])
        
        channels = "channel_1=%d channel_2=%d channel_3=%s" % (
            c1 + 1, c2 + 1, c3 >= 0 and str(c3 + 1)  or '[None]')
        
        out.write("""// Stack colocalisation analyser macro
open("%s");
run("Stack to Hyperstack...", "order=xyzct channels=%d slices=%d frames=%d");
run("Stack Colocalisation Analyser", "%s %s");
close();
""" % (name, img.getSizeC(), img.getSizeZ(), img.getSizeT(), args, channels))

    out.close()

    # Run ImageJ
    try:
        args = ["java", "-cp", IMAGEJ_CLASSPATH, 
            "-Djava.awt.headless=true",
            "ij.ImageJ", "-ijpath", IMAGEJ_PATH, "-batch", macro_file]
        
        # debug
        cmd = " ".join(args)
        print "Script command = %s" % cmd
    
        file = open(result_file, 'wb')
        
        # Run the command
        result = subprocess.call(args, stdout=file)
        if result:
            print >>sys.stderr, "Execution failed with code: %d" % result
        else:
            results = extract_results(result_file)

    except OSError, e:
        print >>sys.stderr, "Execution failed:", e

    # Delete temp files
    try:
        for name in glob.glob("%s/*" % tmp_dir):
            os.remove(name)
    except:
        pass

    return results

def extract_images(conn, images):
    """
    Extracts the images from OMERO.
    
    @param conn:   The BlitzGateway connection
    @param images: The list of images
    """
    global tmp_dir
    
    names = []
    tmp_dir = tempfile.mkdtemp(prefix='colocalisation')
    
    for img in images:
        if img is None:
            continue
        
        name = '%s/%s.ome.tif' % (tmp_dir, img.getId())
        e = conn.createExporter();
        e.addImage(img.getId());
    
        # Use a finally block to ensure clean-up of the exporter
        try:
            length = e.generateTiff()
            out = open(name, 'wb')

            read = 0
            while True:
                buf = e.read(read, 1000000);
                out.write(buf)
                if len(buf) < 1000000:
                    break
                read += len(buf);
                
            out.close()
        finally:
            e.close();

        names.append(name)

    return names

def find_channel_index(img, c):
    """
    Find the channel index (zero based) corresponding to the channel name/index.
    Returns -1 if no channel found.
    
    @param img:   The image
    @param c:     The channel name/index
    """
    for index, ch in enumerate(img.getChannels()):
        if ch.getName() == c or str(index + 1) == c:
            return index
    return -1

def check_parameters(conn, images, params):
    """
    For each image check that the parameters for the channels and frames are OK.
    Return False if any check failed.
    
    @param conn:   The BlitzGateway connection
    @param images: The list of images
    @param params: The script parameters
    """
    result = True
    
    # Check the channel exist
    C = [ params[PARAM_CHANNEL1], params[PARAM_CHANNEL2] ]
    if params[PARAM_CHANNEL3]:
        C.append(params[PARAM_CHANNEL3])
    
    for img in images:
        if (img != None):
            # Channels
            for c in C:
                if find_channel_index(img, c) < 0:
                    print ("ERROR: Image %d: %s does not have channel: %s" % 
                        (img.getId(), img.getName(), c))
                    result = False

    if params[PARAM_MAX_SHIFT] <= params[PARAM_MIN_SHIFT]:
        print ("ERROR: Maximum shift (%d) is not greater than minimum shift (%d)" % 
            (params[PARAM_MAX_SHIFT], params[PARAM_MIN_SHIFT]))
        result = False

    if not params[PARAM_UPLOAD_RESULTS] and not params[PARAM_EMAIL_RESULTS]:
        print ("ERROR: No results option selected")
        result = False

    return result

def run(conn, params):
    """
    For each image defined in the script parameters run the correlation analyser
    and load the result into OMERO.
    Returns the number of images processed or (-1) if there is a 
    parameter error).
    
    @param conn:   The BlitzGateway connection
    @param params: The script parameters
    """
    global tmp_dir
    
    print "Parameters = %s" % params
    
    if not params.get(PARAM_IDS):
        return -1
    
    images = []
    if params.get(PARAM_DATATYPE) == 'Image':
        objects = conn.getObjects("Image", params[PARAM_IDS])
        images = list(objects)
    else:
        for dsId in params[PARAM_IDS]:
            ds = conn.getObject("Dataset", dsId)
            if ds:
                for i in ds.listChildren():
                    images.append(i)
    
    if not check_parameters(conn, images, params):
        return -1

    # Extract images
    image_names = extract_images(conn, images)
    
    # Run ImageJ
    results = run_imagej(conn, images, image_names, params)

    if results:
        # Upload results
        upload_results(conn, results, params)
        
        report = create_report(conn, results, params)
        for line in report:
            print line
            
        # E-mail the result to the user
        email_results(conn, results, report, params)
        
    elif image_names:
        print "ERROR: No results generated for %d images" % len(image_names)

    os.rmdir(tmp_dir)

    return len(results)

def validate_email(conn, params):
    """
    Checks that a valid email address is present for the user_id
    
    @param conn:   The BlitzGateway connection
    @param params: The script parameters
    """
    userEmail = ''
    if params[PARAM_EMAIL]:
        userEmail = params[PARAM_EMAIL]
    else:
        user = conn.getUser()
        userId = user.getName() # Initialises the proxy object for simpleMarshal 
        dic = user.simpleMarshal()
        if 'email' in dic and dic['email']:
            userEmail = dic['email']
        
    params[PARAM_EMAIL] = userEmail
    
    # Validate with a regular expression. Not perfect but it will do for most stuff.
    return re.match("^[a-zA-Z0-9._%-]+@[a-zA-Z0-9._%-]+.[a-zA-Z]{2,6}$", 
                    userEmail)
    
def create_script_defaults():
    """
    Returns a dictionary of the default script parameters
    """
    params = {}

    # Initialise non-optional parameters
    params[PARAM_CHANNEL1] = '1'
    params[PARAM_CHANNEL2] = '2'
    params[PARAM_CHANNEL3] = None
    params[PARAM_METHOD] = 'Otsu'
    params[PARAM_PERMUTATIONS] = 100
    params[PARAM_MIN_SHIFT] = 9
    params[PARAM_MAX_SHIFT] = 16
    params[PARAM_SIGNIFICANCE] = 0.05
    params[PARAM_UPLOAD_RESULTS] = False
    params[PARAM_EMAIL_RESULTS] = True
    params[PARAM_EMAIL] = None
    return params    

def run_as_program():
    """
    Testing function to allow the script to be called outside of the OMERO scripting
    environment. The connection details and image ID must be valid.
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
    conn.keepAlive()
    
    params = create_script_defaults()
    params[PARAM_DATATYPE] = 'Image'
    params[PARAM_IDS] = [51]
    #params[PARAM_DATATYPE] = 'Dataset'
    #params[PARAM_IDS] = [2]
    params[PARAM_UPLOAD_RESULTS] = True
    params[PARAM_EMAIL_RESULTS] = True
    params[PARAM_EMAIL] = ADMIN_EMAIL
    
    count = run(conn, params)
    
    if count >= 0:
        print ("Processed %d image%s" % 
                (count, count != 1 and 's' or ''))

def run_as_script():
    """
    The main entry point of the script, as called by the client via the 
    scripting service, passing the required parameters. 
    """
    params = create_script_defaults()
    methods = []
    for m in ["Li", "MaxEntropy", "Mean", "MinError(I)",
            "Moments", "None", "Otsu", "Percentile", "RenyiEntropy",
            "Triangle", "Yen"]:
        methods.append(rstring(m))
    dataTypes = [rstring('Dataset'),rstring('Image')]
    
    client = scripts.client('Colocalisation_Analyser.py', """\
Perform colocalisation analysis on the image channels. 

Analysis is done using the Confined Displacement Algorithm (CDA). Images are 
displaced a random amount and the colocalisation metric computed. A distribution
is constructed for the metric using multiple displacements and used to assess
the significance of the native result.

Processes a stack image with multiple channels. Each frame is processed separately. 
Extracts the channels (collating z-stacks) and performs:

- (1). Thresholding to create a mask for each channel
- (2). CDA analysis of channel 1 vs channel 2, optionally within the region 
  defined by channel 3
  
Results are appended to the image as a file attachment and/or e-mailed
to you. Messages use your e-mail address from your OMERO profile (or the address 
specified).

See: http://www.sussex.ac.uk/gdsc/intranet/microscopy/omero/scripts/colocalisation""", 
    
    scripts.String(PARAM_DATATYPE, optional=False, grouping="1",
        description="Choose Images via their 'Dataset' or directly by 'Image' IDs.", values=dataTypes, default="Image"),
        
    scripts.List(PARAM_IDS, optional=False, grouping="2",
        description="List of Image IDs").ofType(rlong(0)),
    
    scripts.String(PARAM_CHANNEL1, optional=False, grouping="3", 
        default=params[PARAM_CHANNEL1],
        description="Select the first channel"),
    scripts.String(PARAM_CHANNEL2, optional=False, grouping="4", 
        default=params[PARAM_CHANNEL2],
        description="Select the second channel"),
    scripts.String(PARAM_CHANNEL3, grouping="5", 
        default=params[PARAM_CHANNEL3],
        description="Select the third channel"),
        
    scripts.String(PARAM_METHOD, optional=False, grouping="6", 
        values=methods,
        default=params[PARAM_METHOD],
        description="Select the thresholding method"),

    scripts.Int(PARAM_PERMUTATIONS, optional=False, grouping="7.1", 
        default=params[PARAM_PERMUTATIONS], min=1,
        description="The number of permutations to calculate"),
    scripts.Int(PARAM_MIN_SHIFT, optional=False, grouping="7.2", 
        default=params[PARAM_MIN_SHIFT], min=1,
        description="The minimum shift for random displacements"),
    scripts.Int(PARAM_MAX_SHIFT, optional=False, grouping="7.3", 
        default=params[PARAM_MAX_SHIFT], min=2,
        description="The maximum shift for random displacements"),
    scripts.Float(PARAM_SIGNIFICANCE, optional=False, grouping="7.4", 
        default=params[PARAM_SIGNIFICANCE], min=0, max=1,
        description="The p-value for significance"),

    scripts.Bool(PARAM_UPLOAD_RESULTS, grouping="8", 
        default=params[PARAM_UPLOAD_RESULTS],
        description="Attach the results to each image"),
    scripts.Bool(PARAM_EMAIL_RESULTS, grouping="9", 
        default=params[PARAM_EMAIL_RESULTS],
        description="E-mail the results"),
    scripts.String(PARAM_EMAIL, grouping="9.1", default=params[PARAM_EMAIL],
        description="Specify e-mail address"),

    version = "1.0",
    authors = ["Alex Herbert", "GDSC"],
    institutions = ["University of Sussex"],
    contact = "a.herbert@sussex.ac.uk",
    ) 
    
    try:
        conn = BlitzGateway(client_obj=client)
        conn.keepAlive()
        
        # Process the list of args above. 
        for key in client.getInputKeys():
            if client.getInput(key):
                params[key] = client.getInput(key, unwrap=True)
        
        if params[PARAM_EMAIL_RESULTS] and not validate_email(conn, params):
            client.setOutput("Message", rstring("No valid email address"))
            return

        # Call the main script - returns the number of images processed
        count = run(conn, params)
        
        if count >= 0:
            client.setOutput("Message", 
                rstring("Processed %d image%s" % 
                    (count, count != 1 and 's' or '')))
        else:
            client.setOutput("Message", 
                rstring("Errors found in the input parameters. \
Check the Info file."))

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
    