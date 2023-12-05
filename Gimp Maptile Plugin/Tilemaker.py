#!/usr/bin/env python
import os
import time
import threading
import traceback
import hashlib
import json
from gimpfu import gimp, main, pdb, PF_IMAGE, PF_DRAWABLE, PF_DIRNAME, PF_SPINNER, register

# Heavily adapted from https://bitbucket.org/zmasek/gimp-leaflet/src/master/README.rst
# Tested against GIMP 2.10.32 (revision 1)

BOX = 256
ZOOM_DEFAULT = 8
ZOOM_OPTIONS = (0, 8, 1)
THREAD_OPTIONS = (1, 24, 1)
THREADPOOL = 10

configFile = "config.json"

class Tile:
    
    def __init__(self, x, y, z, image, output_dir, configData):      
        self.x = x
        self.y = y
        self.z = z
        self.image = image
        self.status = "Not Done"
        self.output_dir = output_dir
        self.configData = configData

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
        output_path = os.path.join(self.output_dir, str(self.z), str(self.x), str(self.y) + '.jpg')
        output_directory = os.path.dirname(output_path)
        if not os.path.exists(output_directory):
            try:
                os.makedirs(output_directory)
            except:
                # The threading model sometimes means two tiles will both try to create a directory.  
                # Ignore that exception so the tile can still create the image even if the directory was created by another tile.
                pass
                
        return output_path

    def create_tile(self):
        """
        Create a tile in the calculated coordinates and save it to a disk.
        """

        output_path = self.get_output_path()
        skipped = 0
        
        # gimp.message('Creating a tile...')
        new_image = self.image.duplicate()
        offset_x = self.x * BOX
        offset_y = self.y * BOX    
        pdb.gimp_image_crop(new_image, BOX, BOX, offset_x, offset_y)
        
        # Register the md5 of the image for rerunnability 
        md5 = self.md5_of_image(new_image)
        if md5 == self.configData["files"].get(self.uniqueKey(), {}).get("md5", "DNE"):
            self.status = "Skipped"
        else:
            # TODO: Check to see if a tile exists at that location already, and if so, get its MD5 for comparison.  
            # This will increase rerunability for interrupted runs, at the cost of some performance.
            self.configData["files"][self.uniqueKey()] = {}
            self.configData["files"][self.uniqueKey()]["md5"] = md5
            pdb.file_jpeg_save(new_image, new_image.active_layer, output_path, output_path, 0.9, 0, 0, 0,'Creating with GIMP', 0, 0, 0, 0)
            pdb.gimp_image_delete(new_image)
            self.status = "Done"

        return self.status
    
    def uniqueKey(self):
        return "(" + str(self.z) + "," + str(self.x) + "," + str(self.y) + ")"
        
    def details(self):
        description = self.uniqueKey() + " at " + self.output_dir
    
        return description
    
class WorkQueue:
    def __init__(self, configData):
        self.thread = threading.Thread(target=self.process_work_queue, args=())
        self.queue = []
        self.notdone = 0
        self.done = 0
        self.skipped = 0
        self.error = 0
        self.configData = configData
        
    # Given a queue of work, cycle through it and create tiles.
    def process_work_queue(self):
        # gimp.message("Processing work queue: " + str(len(self.queue)))
        self.notdone = len(self.queue) 
        
        for workitem in self.queue:
            status = "None"
            try:
                status = workitem.create_tile() 
                time.sleep(.05) # Brief pause to allow main thread to receive updates.
            except Exception as e:
                status = "Error"
                workitem.status = status
                gimp.message("Error in tile creation: " + str(e))
                self.configData["errors"]["log"][workitem.uniqueKey()] = str(e)                
            finally:
                if status == "Error":
                    self.error = self.error + 1
                elif status == "Skipped":
                    self.skipped = self.skipped + 1
                else:
                    self.done = self.done + 1
                
                self.notdone = self.notdone - 1
                self.configData["files"][workitem.uniqueKey()]["status"] = status
                
    def addWork(self, tile):
        self.queue.append(tile)
        
    def start(self):
        # gimp.message("Thread Initiated")    
        self.thread.start()
        
    def is_alive(self):
        return self.thread.is_alive()
        
    def join(self):
        self.thread.join() 
 
 
def safe_output_path(image, prefix, output_dir):
    output_path = os.path.join(output_dir, prefix + image.name + ".jpg")

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
    skipped = 0
    
    for worklist in queueList:
        notdone = notdone + worklist.notdone
        done = done + worklist.done
        error = error + worklist.error
        skipped = skipped + worklist.skipped
        
        if worklist.is_alive():
            active = active + 1
                
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
        new_width = dimension
        new_height = new_width * height / width
    else:
        new_height = dimension
        new_width = new_height * width / height
    pdb.gimp_image_scale(image, new_width, new_height)
    pdb.gimp_image_crop(image, dimension, dimension, 0, 0)

def loadConfigData(output_dir):
    if os.path.exists(os.path.join(output_dir, configFile)):
         
        # Reading config file, if it exists
        with open(os.path.join(output_dir, configFile), "r") as infile:
            data = json.load(infile)
            # gimp.message(json.dumps(data, indent=4))
    else:
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
    
def saveConfigData(output_dir, data):
    # Serializing json
    json_object = json.dumps(data, indent=4)
     
    # Writing to sample.json
    with open(os.path.join(output_dir, configFile), "w") as outfile:
        outfile.write(json_object)        

def leaflet_tile(image, layer, output_dir, zoom_level, numthreads):
    """
    Tiles the image for use in Leaflet maps.

    Parameters:
    output_dir : string The folder in which to save the produced tiles.
    """
    # gimp.message("Initializing Tiling Logic")

    zoomImageMap = {}
    workQueueList = []

    configData = loadConfigData(output_dir)
    
    # Ensure we are not maniuplating the source image - just a copy of it.    
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
    pdb.file_jpeg_save(temp_img, temp_img.active_layer, output_path, output_path, 0.9, 0, 0, 0,'Creating with GIMP', 0, 0, 0, 0) 
    
    # Initialize our list of lists for holding threaded work queues
    for tp in xrange(numthreads):
        workQueueList.append(WorkQueue(configData))
    
    # prepare_initial_image(temp_img, dimension, output_dir)
    scaledDimension = dimension
    
    # Scale a source image for each zoom level.
    for z in xrange(zoom_level, -1, -1):
        # The min zoom is the point at which the map size is no longer evenly divisible into BOX-sized chunks.
        if scaledDimension % BOX == 0:
            zoomed_img = temp_img.duplicate()
            temp_img.disable_undo()
            zoomImageMap[z] = zoomed_img
            scaledDimension /= 2
            pdb.gimp_image_scale(temp_img, scaledDimension, scaledDimension)
            min_zoom = z
    
    configData["minzoom"] = min_zoom
    
    thumbnail = zoomImageMap[min_zoom]
    output_path = safe_output_path(thumbnail, "thumbnail_", output_dir)
    pdb.file_jpeg_save(thumbnail, thumbnail.active_layer, output_path, output_path, 0.9, 0, 0, 0,'Creating with GIMP', 0, 0, 0, 0)     
    
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
                    newTile = Tile(x, y, z, zoomImageMap[z], output_dir, configData)

                    workQueueList[threadallocator].addWork(newTile)
                    threadallocator = threadallocator + 1
                    if threadallocator >= numthreads:
                        threadallocator = 0
                        
        pdb.gimp_progress_update(float(z)/float(zoom_level)) 

    gimp.progress_init ("Tiling " + str(maxtiles) + " tiles.")    
    # Create threaded lists that divide up the work of the entire list of tile items.
    for workqueue in workQueueList:
        # gimp.message("Queuesize: " + str(len(workqueue.queue)))
        try:
            workqueue.start()
            # gimp.message("Launched work queue.")
            # workqueue.join()
        except:
            gimp.message("Failed to launch work queue.")
       
    pdb.gimp_progress_set_text("All work queues started.")         
    active = status_check(workQueueList, configData)
        
    while active > 0:
        time.sleep(3) # Brief pause to not consume CPU with constant status checks while threads are working.
        active = status_check(workQueueList, configData)         
                
    pdb.gimp_progress_set_text('Tiling Complete!')
    saveConfigData(output_dir, configData)

register(
    'Tilemaker',
    'Create leaflet tiles for current image.',
    'Tiles the image and saves the output ready for use in leaflet maps',
    'Al Mele',
    'GNU GPL v3',
    '2023',
    '<Image>/Filters/Tilemaker/Make Map Tiles',
    '*',
    [
        (PF_IMAGE, 'image', 'Input image', None),
        (PF_DRAWABLE, 'drawable', 'Input drawable', None),
        (PF_DIRNAME, 'output_dir', 'Output directory', "C:\\temp\\tiles"),
        (PF_SPINNER, 'zoom_level', 'Zoom level', ZOOM_DEFAULT, ZOOM_OPTIONS),
        (PF_SPINNER, 'numthreads', 'Thread pool size', THREADPOOL, THREAD_OPTIONS)
    ],
    [],
    leaflet_tile,
    menu='<Image>/Filters/Tilemaker/Make Map Tiles'
)

main()
