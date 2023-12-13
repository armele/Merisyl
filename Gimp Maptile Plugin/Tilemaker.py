#!/usr/bin/env python
import os
import time
import threading
import traceback
import hashlib
import json
import copy
from Queue import Queue
from gimpfu import *

# Heavily adapted from https://bitbucket.org/zmasek/gimp-leaflet/src/master/README.rst
# Tested against GIMP 2.10.32 (revision 1)
# Test scenarios:
#   New map from scratch (empty target)
#   Regenerate with modifications
#   Regenerate with missing files.
#   Regenerate with files that exist and are not reflected in MD5 map.

BOX = 256
ZOOM_DEFAULT = 8
ZOOM_OPTIONS = (0, 8, 1)
THREAD_OPTIONS = (1, 8, 1)
THREADPOOL = 4
FILE_TYPE = ".png"

configFile = "config.json"

# Lock for protecting access to the shared dictionary
lock = threading.Lock()

class Tile:
    
    def __init__(self, x, y, z, image, output_dir, existingFiles, previousConfigData, skipexisting):      
        self.x = x
        self.y = y
        self.z = z
        self.image = image
        self.status = "Not Done"
        self.output_dir = output_dir
        self.skipexisting = skipexisting
        self.existingFiles = existingFiles
        self.previousConfigData = previousConfigData

    def md5_of_image(self, image):
        # Get the active drawable from the image (usually the currently selected layer)
        active_drawable = pdb.gimp_image_get_active_drawable(image)
        
        # Check if the active drawable exists and is compatible
        if active_drawable is None:
            pdb.gimp_message("No drawable found in the image.")
            return
        
        # Get pixel data of the drawable
        pixels = bytearray(active_drawable.get_pixel_rgn(0, 0, active_drawable.width, active_drawable.height, False, False)[0:active_drawable.width, 0:active_drawable.height])
        
        # Calculate MD5 hash of the pixel data
        md5_hash = hashlib.md5(pixels).hexdigest()
        
        # Display the MD5 hash in GIMP's console
        # pdb.gimp_message("MD5 hash of the image: " + md5_hash) 
        return md5_hash
        
    def get_output_path(self):
        """
        Create the path for saving an image. If the path folders don't exist, create them as well.
        """
        output_path = os.path.join(self.output_dir, str(self.z), str(self.x), str(self.y) + FILE_TYPE)
        output_directory = os.path.dirname(output_path)
        if not os.path.exists(output_directory):
            try:
                os.makedirs(output_directory)
            except:
                # The threading model sometimes means two tiles will both try to create a directory.  
                # Ignore that exception so the tile can still create the image even if the directory was created by another tile.
                pass
                
        return output_path

    def getPreviousMD5(self, key):
        prevMD5 = self.previousConfigData.get("files", {}).get(key, {}).get("md5", "DNE") 
        # gimp.message(prevMD5)
        return prevMD5

    def create_tile(self):
        """
        Create a tile in the calculated coordinates and save it to storage.
        """
        tileResult = {}
        tileResult["key"] = self.uniqueKey()  
        tileResult["filename"] = self.get_output_path()
        
        writefile = True
        
        # gimp.message('Creating a tile...')
        new_image = self.image.duplicate()
        offset_x = self.x * BOX
        offset_y = self.y * BOX    
        pdb.gimp_image_crop(new_image, BOX, BOX, offset_x, offset_y)
        
        if not pdb.gimp_drawable_is_indexed(new_image.active_layer):
            pdb.gimp_image_convert_indexed(new_image, 1, 0, 256, False, False, "")
        
        # Register the md5 of the image for rerunnability 
        tileResult["md5"] = self.md5_of_image(new_image)
        
        # If we are not checking the existing tile for changes, just set the previous MD5 to the current one.
        if self.skipexisting and tileResult["filename"] in self.existingFiles:
            prevMD5 = tileResult["md5"]
        else:
            prevMD5 = self.getPreviousMD5(self.uniqueKey())
        
        # We have a MD5 configured, and the file exists.
        if tileResult["md5"] == prevMD5:
            writefile = False
            # tileResult["debug"] = "Matched previous md5"
        else:
            # MD5s don't match, or we don't have an MD5 registered, but the file exists.
            if tileResult["filename"] in self.existingFiles:
                # existing_image = pdb.file_jpeg_load(tileResult["filename"], tileResult["filename"])
                existing_image = pdb.file_png_load(tileResult["filename"], tileResult["filename"])
                existingmd5 = self.md5_of_image(existing_image)
                
                if tileResult["md5"] == existingmd5:
                    writefile = False
                    # tileResult["debug"] = "Matched unregistered md5 of existing file."
                else:
                    writefile = True
                    # tileResult["debug"] = "No match with unregistered md5 of existing file."
                
        if writefile:
            # pdb.file_jpeg_save(new_image, new_image.active_layer, tileResult["filename"], tileResult["filename"], 1.0, 0, 0, 0,'Creating with GIMP', 0, 0, 0, 0)
            pdb.file_png_save(new_image, new_image.active_layer, tileResult["filename"], tileResult["filename"], 0, 0, 0, 0, 0, 0, 0)
            self.status = "Done"
        else:            
            self.status = "Skipped"
        
        pdb.gimp_image_delete(new_image)
            
        tileResult["status"] = self.status
        
        return tileResult
    
    def uniqueKey(self):
        return "(" + str(self.z) + "," + str(self.x) + "," + str(self.y) + ")"
        
    def details(self):
        description = self.uniqueKey() + " at " + self.output_dir
    
        return description
    
class WorkQueue:
    def __init__(self, communicationQueue, num):
        self.thread = threading.Thread(target=self.process_work_queue, args=())
        self.work = []
        self.notdone = 0
        self.done = 0
        self.skipped = 0
        self.error = 0
        self.queueNumber = num
        self.communicationQueue = communicationQueue
        
    # Given a queue of work, cycle through it and create tiles.
    def process_work_queue(self):
        # gimp.message("Processing work queue: " + str(+ self.queueNumber + ", items: " + len(self.work)))
        self.notdone = len(self.work) 
        
        for workitem in self.work:
            status = "None"
            try:
                tileResult = workitem.create_tile() 
                tileResult["queueNumber"] = self.queueNumber
                self.communicationQueue.put(tileResult)
                time.sleep(.2) # Brief pause to allow main thread to receive updates.
            except Exception as e:
                status = "Error"
                workitem.status = status
                gimp.message("Error in tile creation: " + str(e))
                tileResult = {}
                tileResult[workitem.uniqueKey] = str(e)
                tileResult["error"] = str(e)
                tileResult["queueNumber"] = self.queueNumber
                self.communicationQueue.put(tileResult)                
            finally:
                if tileResult["status"] == "Error":
                    self.error = self.error + 1
                elif tileResult["status"] == "Skipped":
                    self.skipped = self.skipped + 1
                else:
                    self.done = self.done + 1
                
                self.notdone = self.notdone - 1
                # gimp.message(json.dumps(tileResult))
                
        # gimp.message("Completed work queue: " + str(len(self.work)))
          
    def addWork(self, tile):
        self.work.append(tile)
        
    def start(self):
        # gimp.message("Thread Initiated")    
        self.thread.start()
        
    def is_alive(self):
        return self.thread.is_alive()
        
    def join(self):
        self.thread.join()
 
def safe_output_path(image, prefix, output_dir):
    output_path = os.path.join(output_dir, prefix + image.name + FILE_TYPE)

    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except:
            # The threading model sometimes means two tiles will both try to create a directory.  
            # Ignore that exception so the tile can still create the image even if the directory was created by another tile.
            pass
            
    return output_path

 
def calc_dimension(zoom_level, image):
    #dimension = pow(2, zoom_level + 8)
    dimension = max(image.width, image.height)
    
    if (dimension % 4096):
        dimension = int(dimension + (4096 - (dimension % 4096)))
        
    return dimension

def count_all_status(queueList):
    notdone = 0
    done = 0
    error = 0
    active = 0
    inactive = 0
    skipped = 0
    
    for worklist in queueList:
        notdone = notdone + worklist.notdone
        done = done + worklist.done
        error = error + worklist.error
        skipped = skipped + worklist.skipped
        
        if worklist.is_alive():
            active = active + 1
        else:
            inactive = inactive + 1
            
    # gimp.message("Active: " + str(active) + ", " + "Inactive: " + str(inactive))
                
    return [notdone, done, error, active, skipped]

def status_check(queueList, configData):
    counts = count_all_status(queueList)
    notdone = counts[0]
    done = counts[1]
    error = counts[2]
    active = counts[3]
    skipped = counts[4]
    
    progress = float(done + skipped + error) / float(done + skipped + notdone + error)
    
    configData["errors"]["count"] = error
    configData["status"]["done"] = done
    configData["status"]["notdone"] = notdone
    configData["status"]["skipped"] = skipped
    configData["status"]["progress"] = progress
    
    pdb.gimp_progress_set_text("Active Threads: " + str(active) + ", Done: " + str(done + skipped) + " (" + str(int(progress * 100)) + "%)")
    pdb.gimp_progress_update(progress) 
        
    return active

def prepare_image(image, layer, dimension):
    """
    Prepare the image by scaling to the adequate resolution.
    """
    width = layer.width
    height = layer.height
    if width < height:
        new_height = dimension
        new_width = new_height * width / height
    else:
        new_width = dimension
        new_height = new_width * height / width
        
    pdb.gimp_progress_set_text("Scaling source image.")
    pdb.gimp_image_scale(image, new_width, new_height)
    # pdb.gimp_image_crop(image, dimension, dimension, 0, 0)

def initializeConfig():
    # Initialize a new set of config data.
    data = {}
    data["minzoom"] = 0
    data["files"] = {}
    data["errors"] = {}
    data["status"] = {}
    data["errors"]["count"] = 0        
    data["errors"]["log"] = {}
    # gimp.message("New configuration created.")
    
    return data

def loadPreviousConfig(output_dir):
    if os.path.exists(os.path.join(output_dir, configFile)):
         
        # Reading config file, if it exists
        with open(os.path.join(output_dir, configFile), "r") as infile:
            data = json.load(infile)
            data["status"] = {}
            data["errors"]["count"] = 0        
            data["errors"]["log"] = {}
            
            # On a rerun, mark tiles as "To Verify". This will get replaced with this runs processing of them.
            for tiledata in data["files"]:
                # gimp.message(json.dumps(tiledata))
                data["files"][tiledata]["status"] = "To Verify"

        return data
    
def saveConfigData(output_dir, data):
    # Serializing json
    json_object = json.dumps(data, indent=4)
     
    # Writing to json
    with open(os.path.join(output_dir, configFile), "w") as outfile:
        outfile.write(json_object)        

# When gimp supports python 3.5+, replace this with scandir
def list_files_recursive(directory):
    file_paths = []
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            file_paths.append(file_path)
        elif os.path.isdir(file_path):
            file_paths.extend(list_files_recursive(file_path))
    return file_paths

def inventoryExistingFiles(output_dir):
    gimp.progress_init("Inventorying existing files.")  
    
    existingFiles = list_files_recursive(output_dir)
    
    return existingFiles
    # Approach below is quite slow.
    # for root, directories, files in os.walk(output_dir):
    #    for file in files:
    #        existingFiles[os.path.join(root, file)] = True     

def leaflet_tile(image, layer, output_dir, zoom_level, numthreads, skipexisting):
    """
    Tiles the image for use in Leaflet maps.

    Parameters:
    output_dir : string The folder in which to save the produced tiles.
    """
    # gimp.message("Initializing Tiling Logic")

    zoomImageMap = {}
    workQueueList = []

    configData = initializeConfig()
    previousConfigData = loadPreviousConfig(output_dir)
    existingFiles = inventoryExistingFiles(output_dir)
    
    # Assisting Debug
    # configData["existingFiles"] = existingFiles
    # configData["previousConfigData"] = previousConfigData
    
    # Ensure we are not maniuplating the source image - just a copy of it.    
    gimp.progress_init("Preparing source image.") 
    temp_img = image.duplicate()
    temp_img.disable_undo()

    zoom_level = int(zoom_level)   
    numthreads = int(numthreads)
    min_zoom = zoom_level
        
    # Scale the image to a square image in multiples of 256, and save out a copy of this inital starting image (full map size) for point mapping purposes.
    dimension = calc_dimension(zoom_level, temp_img)
     
    prepare_image(temp_img, layer, dimension)
    pdb.gimp_image_resize(temp_img, dimension, dimension, (dimension - temp_img.width) / 2, (dimension - temp_img.height) / 2) #Make it square and center
    pdb.gimp_layer_resize_to_image_size(temp_img.active_layer)
    
    output_path = safe_output_path(image, "template_", output_dir)
    # pdb.file_jpeg_save(temp_img, temp_img.active_layer, output_path, output_path, 0.9, 0, 0, 0,'Creating with GIMP', 0, 0, 0, 0) 
    pdb.file_png_save(temp_img, temp_img.active_layer, output_path, output_path, 0, 0, 0, 0, 0, 0, 0)
    
    # Initialize our list of lists for holding threaded work queues
    communicationQueue = Queue()
    queueNumber = 0
    for tp in xrange(numthreads):
        workQueueList.append(WorkQueue(communicationQueue, queueNumber))
        queueNumber = queueNumber + 1
    
    # prepare_initial_image(temp_img, dimension, output_dir)
    scaledDimension = dimension
    
    # Scale a source image for each zoom level.
    gimp.progress_init("Preparing zoom masters.") 
    for z in xrange(zoom_level, -1, -1):
        # The min zoom is the point at which the map size is no longer evenly divisible into BOX-sized chunks.
        if scaledDimension % BOX == 0:
            zoomed_img = temp_img.duplicate()
            temp_img.disable_undo()
            zoomImageMap[z] = zoomed_img
            scaledDimension /= 2
            pdb.gimp_image_scale(temp_img, scaledDimension, scaledDimension)
            min_zoom = z
    
        pdb.gimp_progress_update(float(z)/float(zoom_level)) 
        
    configData["minzoom"] = min_zoom
    
    
    thumbnail = zoomImageMap[min_zoom]
    output_path = safe_output_path(thumbnail, "thumbnail_", output_dir)
    # pdb.file_jpeg_save(thumbnail, thumbnail.active_layer, output_path, output_path, 0.9, 0, 0, 0,'Creating with GIMP', 0, 0, 0, 0)     
    pdb.file_png_save(thumbnail, thumbnail.active_layer, output_path, output_path, 0, 0, 0, 0, 0, 0, 0)
            
    maxtiles = 0
    threadallocator = 0
    
    gimp.progress_init("Registering zoom layers.")     
    for z in xrange(zoom_level, -1, -1):
        # Don't bother trying to create tiles for zoom levels for which no image was created.
        if z in zoomImageMap:
            scaledDimension = zoomImageMap[z].width
            for x in xrange(scaledDimension / BOX):
                for y in xrange(scaledDimension / BOX):
                    maxtiles = maxtiles + 1
                    newTile = Tile(x, y, z, zoomImageMap[z], output_dir, existingFiles, previousConfigData, skipexisting)

                    workQueueList[threadallocator].addWork(newTile)
                    threadallocator = threadallocator + 1
                    if threadallocator >= numthreads:
                        threadallocator = 0
                        
        pdb.gimp_progress_update(float(z)/float(zoom_level)) 

    gimp.progress_init ("Tiling " + str(maxtiles) + " tiles.")    
    # Create threaded lists that divide up the work of the entire list of tile items.
    for workqueue in workQueueList:
        # gimp.message("Queuesize: " + str(len(workqueue.work)))
        try:
            workqueue.start()
            # gimp.message("Launched work queue.")
            # workqueue.join()
        except:
            gimp.message("Failed to launch work queue.")
       
    pdb.gimp_progress_set_text("All work queues started.")         
    active = status_check(workQueueList, configData)
    
    tileDoneCount = 0
    while active > 0 or not communicationQueue.empty():

        while not communicationQueue.empty():
            tileResult = communicationQueue.get()
            configData["files"][tileResult["key"]] = tileResult
            tileDoneCount = tileDoneCount + 1
        
            if tileDoneCount % 20 == 0:
                active = status_check(workQueueList, configData)
                # gimp.message("Active: " + str(active))
                
            if tileDoneCount % 50 == 0:
                # Periodically save intermediate progress
                saveConfigData(output_dir, configData)

        if active == 0:
            pdb.gimp_progress_set_text("Saving Results.")
            pdb.gimp_progress_update(float(maxtiles - communicationQueue.qsize()) / float(maxtiles))
        else:
            time.sleep(.2) # Brief pause to not consume CPU with constant unthrottled loop while threads are working.
            active = status_check(workQueueList, configData)            
    
    # gimp.message("Main loop complete.")
    
    pdb.gimp_progress_set_text('Tiling Complete!')
    saveConfigData(output_dir, configData)

register(
    'Tilemaker',
    'Create leaflet tiles for current image.',
    'Tiles the image and saves the output ready for use in leaflet maps',
    'Al Mele',
    'GNU GPL v3',
    '2023',
    '<Image>/Filters/Tilemaker',
    '*',
    [
        (PF_IMAGE, 'image', 'Input image', None),
        (PF_DRAWABLE, 'drawable', 'Input drawable', None),
        (PF_DIRNAME, 'output_dir', 'Output directory', 'C:\\temp\\tiles'),
        (PF_SPINNER, 'zoom_level', 'Zoom level', ZOOM_DEFAULT, ZOOM_OPTIONS),
        (PF_SPINNER, 'numthreads', 'Thread pool size', THREADPOOL, THREAD_OPTIONS),
        (PF_TOGGLE, "skipexisting", "Skip Existing Tiles", True)
    ],
    [],
    leaflet_tile,
    menu='<Image>/Filters/Tilemaker/Make Map Tiles'
)

main()
