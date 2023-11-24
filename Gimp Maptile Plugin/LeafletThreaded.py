#!/usr/bin/env python
import os
import time
import threading
import traceback
from gimpfu import gimp, main, pdb, PF_IMAGE, PF_DRAWABLE, PF_DIRNAME, PF_SPINNER, register

# Heavily adapted from https://bitbucket.org/zmasek/gimp-leaflet/src/master/README.rst
# Tested against GIMP 2.10.32 (revision 1)

BOX = 256
ZOOM_DEFAULT = 8
ZOOM_OPTIONS = (0, 8, 1)
THREAD_OPTIONS = (1, 24, 1)
THREADPOOL = 10

threadLock = threading.Lock()

class Tile:
    def __init__(self, x, y, z, image, output_dir):      
        self.x = x
        self.y = y
        self.z = z
        self.image = image
        self.status = "Not Done"
        self.output_dir = output_dir
    
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
        
        if not os.path.exists(output_path):
            # gimp.message('Creating a tile...')
            new_image = self.image.duplicate()
            offset_x = self.x * BOX
            offset_y = self.y * BOX    
            pdb.gimp_image_crop(new_image, BOX, BOX, offset_x, offset_y)
            pdb.file_jpeg_save(new_image, new_image.active_layer, output_path, output_path, 0.9, 0, 0, 0,'Creating with GIMP', 0, 0, 0, 0)
            pdb.gimp_image_delete(new_image)
            self.status = "Done"
        else: 
            self.status = "Skipped"
            # gimp.message('Skipping existing tile.')    

        return self.status
        
    def details(self):
        description = "Zoom " + str(self.z) + " (" + str(self.x) + "," + str(self.y) + ") at " + self.output_dir
    
        return description
    
class WorkQueue:
    def __init__(self):
        self.thread = threading.Thread(target=self.process_work_queue, args=())
        self.queue = []
        self.notdone = 0
        self.done = 0
        self.error = 0   
        
    # Given a queue of work, cycle through it and create tiles.
    def process_work_queue(self):
        # gimp.message("Processing work queue: " + str(len(self.queue)))
        self.notdone = len(self.queue) 
        
        for workitem in self.queue:
            status = "None"
            try:
                status = workitem.create_tile() 
                
            except Exception as e:
                status = "Error"
                workitem.status = status
                gimp.message("Error " + str(e) + " for tile: " + workitem.details())
            finally:
                if status == "Error":
                    self.error = self.error + 1
                else:
                    self.done = self.done + 1
                
                self.notdone = self.notdone - 1
                    
    def addWork(self, tile):
        self.queue.append(tile)
        
    def start(self):
        # gimp.message("Thread Initiated")    
        self.thread.start()
        
    def is_alive(self):
        return self.thread.is_alive()
        
    def join(self):
        self.thread.join() 
 
def inital_image_output_path(image, output_dir):
    output_path = os.path.join(output_dir, "tilebase_" + image.name + ".jpg")

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
    
    for worklist in queueList:
        notdone = notdone + worklist.notdone
        done = done + worklist.done
        error = error + worklist.error
        
        if worklist.is_alive():
            active = active + 1
                
    return [notdone, done, error, active]

def status_check(queueList):
    counts = count_all_status(queueList)
    notdone = counts[0]
    done = counts[1]
    error = counts[2]
    active = counts[3]
    
    progress = float(done + error) / float(done + notdone + error)
    pdb.gimp_progress_set_text("Active Threads: " + str(active) + ", Done: " + str(done) + " (" + str(int(progress * 100)) + "%)")
    pdb.gimp_progress_update(progress) 
        
    return active

def leaflet_tile(image, layer, output_dir, zoom_level, numthreads):
    """
    Tiles the image for use in Leaflet maps.

    Parameters:
    output_dir : string The folder in which to save the produced tiles.
    """
    # gimp.message("Initializing Tiling Logic")

    # Ensure we are not maniuplating the source image - just a copy of it.
    zoomImageMap = {}
    workQueueList = []
    temp_img = image.duplicate()
    temp_img.disable_undo()

    zoom_level = int(zoom_level)   
    numthreads = int(numthreads)
    
    # Scale the image to a square image in multiples of 256, and save out a copy of this one for point mapping purposes.
    dimension = calc_dimension(zoom_level, temp_img)
    pdb.gimp_image_resize(temp_img, dimension, dimension, (dimension - temp_img.width) / 2, (dimension - temp_img.height) / 2)
    pdb.gimp_layer_resize_to_image_size(temp_img.active_layer)
    output_path = inital_image_output_path(image, output_dir)
    pdb.file_jpeg_save(temp_img, temp_img.active_layer, output_path, output_path, 0.9, 0, 0, 0,'Creating with GIMP', 0, 0, 0, 0) 
    
    # Initialize our list of lists for holding threaded work queues
    for tp in xrange(numthreads):
        workQueueList.append(WorkQueue())
    
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

    maxtiles = 0
    threadallocator = 0
    for z in xrange(zoom_level, -1, -1):
        # Don't bother trying to create tiles for zoom levels for which no image was created.
        if z in zoomImageMap:
            scaledDimension = zoomImageMap[z].width
            gimp.progress_init("Registering zoom layer " + str(z) + " with work queue.")
            for x in xrange(scaledDimension / BOX):
                for y in xrange(scaledDimension / BOX):
                    maxtiles = maxtiles + 1
                    newTile = Tile(x, y, z, zoomImageMap[z], output_dir)

                    workQueueList[threadallocator].addWork(newTile)
                    threadallocator = threadallocator + 1
                    if threadallocator >= numthreads:
                        threadallocator = 0

    gimp.progress_init ("Tiling " + str(maxtiles) + " tiles.")    
    
    #TODO: Create a threading call that processes an entire list of tile items.
    for workqueue in workQueueList:
        # gimp.message("Queuesize: " + str(len(workqueue)))
        try:
            workqueue.start()
            # workqueue.join()
        except:
            gimp.message("Failed to launch work queue.")
          

    active = status_check(workQueueList)
        
    while active > 0:
        # time.sleep(3)
        active = status_check(workQueueList)
                
    gimp.message('Tiling Complete!')
    
    # Brief pause to let pending progress updates to clear, and avoid an annoying (and incorrect) message about a possible plugin-crash.
    time.sleep(3)
    

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
