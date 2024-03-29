#! /usr/bin/env python3

# Copyright(c) 2017 Intel Corporation. 
# License: MIT See LICENSE file in root directory.


from mvnc import mvncapi as mvnc
from scipy import optimize
import sys
import numpy
import cv2
import time
import csv
import os
import sys
from sys import argv

# name of the opencv window
cv_window_name = "SSD Mobilenet"

# labels AKA classes.  The class IDs returned
# are the indices into this list
labels = ('background',
          '1', '2', '3','4', '5', 'face')

# the ssd mobilenet image width and height
NETWORK_IMAGE_WIDTH = 300
NETWORK_IMAGE_HEIGHT = 300

# the minimal score for a box to be shown
min_score_percent = 60

# the resize_window arg will modify these if its specified on the commandline
resize_output = False
resize_output_width = 0
resize_output_height = 0

# read video files from this directory
input_video_path = '.'

# create a preprocessed image from the source image that complies to the
# network expectations and return it
def preprocess_image(source_image):
    resized_image = cv2.resize(source_image, (NETWORK_IMAGE_WIDTH, NETWORK_IMAGE_HEIGHT))
    
    # trasnform values from range 0-255 to range -1.0 - 1.0
    resized_image = resized_image - 127.5
    resized_image = resized_image * 0.007843
    return resized_image

# handles key presses by adjusting global thresholds etc.
# raw_key is the return value from cv2.waitkey
# returns False if program should end, or True if should continue
def handle_keys(raw_key):
    global min_score_percent
    ascii_code = raw_key & 0xFF
    if ((ascii_code == ord('q')) or (ascii_code == ord('Q'))):
        return False
    elif (ascii_code == ord('B')):
        min_score_percent += 5
        print('New minimum box percentage: ' + str(min_score_percent) + '%')
    elif (ascii_code == ord('b')):
        min_score_percent -= 5
        print('New minimum box percentage: ' + str(min_score_percent) + '%')

    return True


# overlays the boxes and labels onto the display image.
# display_image is the image on which to overlay the boxes/labels
# object_info is a list of 7 values as returned from the network
#     These 7 values describe the object found and they are:
#         0: image_id (always 0 for myriad)
#         1: class_id (this is an index into labels)
#         2: score (this is the probability for the class)
#         3: box left location within image as number between 0.0 and 1.0
#         4: box top location within image as number between 0.0 and 1.0
#         5: box right location within image as number between 0.0 and 1.0
#         6: box bottom location within image as number between 0.0 and 1.0
# returns None
def overlay_on_image(display_image, object_info, trajectory_queue):
    source_image_width = display_image.shape[1]
    source_image_height = display_image.shape[0]

    base_index = 0
    class_id = object_info[base_index + 1]
    percentage = int(object_info[base_index + 2] * 100)
    if (percentage <= min_score_percent):
        return

    label_text = labels[int(class_id)] + " (" + str(percentage) + "%)"
    box_left = int(object_info[base_index + 3] * source_image_width)
    box_top = int(object_info[base_index + 4] * source_image_height)
    box_right = int(object_info[base_index + 5] * source_image_width)
    box_bottom = int(object_info[base_index + 6] * source_image_height)
    box_center_horizontal = int((box_left + box_right)/2)
    box_center_vertical = int((box_bottom + box_top)/2)

    box_color = (255, 128, 0)  # box color
    box_thickness = 2
    cv2.rectangle(display_image, (box_left, box_top), (box_right, box_bottom), box_color, box_thickness)
    cv2.rectangle(display_image, (box_center_horizontal-1, box_center_vertical+1), (box_center_horizontal+1, box_center_vertical-1), box_color, box_thickness)

    if (object_info[base_index + 1] == 2):
        for i, point in enumerate(trajectory_queue):

            if ( i < 9 ):
                point2 = trajectory_queue[i+1]

                if ( point != (0,0) ):
                    cv2.line(display_image, point, point2, box_color, box_thickness)


    scale_max = (100.0 - min_score_percent)
    scaled_prob = (percentage - min_score_percent)
    scale = scaled_prob / scale_max

    # draw the classification label string just above and to the left of the rectangle
    #label_background_color = (70, 120, 70)  # greyish green background for text
    label_background_color = (0, int(scale * 175), 75)
    label_text_color = (255, 255, 255)  # white text

    label_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
    label_left = box_left
    label_top = box_top - label_size[1]
    if (label_top < 1):
        label_top = 1
    label_right = label_left + label_size[0]
    label_bottom = label_top + label_size[1]
    cv2.rectangle(display_image, (label_left - 1, label_top - 1), (label_right + 1, label_bottom + 1),
                  label_background_color, -1)

    # label text above the box
    cv2.putText(display_image, label_text, (label_left, label_bottom), cv2.FONT_HERSHEY_SIMPLEX, 0.5, label_text_color, 1)

    # display text to let user know how to quit
    cv2.rectangle(display_image,(0, 0),(100, 15), (128, 128, 128), -1)
    cv2.putText(display_image, "Q to Quit", (10, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)



#return False if found invalid args or True if processed ok
def handle_args():
    global resize_output, resize_output_width, resize_output_height
    for an_arg in argv:
        if (an_arg == argv[0]):
            continue

        elif (str(an_arg).lower() == 'help'):
            return False

        elif (str(an_arg).startswith('resize_window=')):
            try:
                arg, val = str(an_arg).split('=', 1)
                width_height = str(val).split('x', 1)
                resize_output_width = int(width_height[0])
                resize_output_height = int(width_height[1])
                resize_output = True
                print ('GUI window resize now on: \n  width = ' +
                       str(resize_output_width) +
                       '\n  height = ' + str(resize_output_height))
            except:
                print('Error with resize_window argument: "' + an_arg + '"')
                return False
        else:
            return False

    return True


# Run an inference on the passed image
# image_to_classify is the image on which an inference will be performed
#    upon successful return this image will be overlayed with boxes
#    and labels identifying the found objects within the image.
# ssd_mobilenet_graph is the Graph object from the NCAPI which will
#    be used to peform the inference.
def run_inference(image_to_classify, ssd_mobilenet_graph, trajectory_queue, gesture_number):

    # preprocess the image to meet nework expectations
    resized_image = preprocess_image(image_to_classify)

    # Send the image to the NCS as 16 bit floats
    ssd_mobilenet_graph.LoadTensor(resized_image.astype(numpy.float16), None)

    # Get the result from the NCS
    output, userobj = ssd_mobilenet_graph.GetResult()

    #   a.	First fp16 value holds the number of valid detections = num_valid.
    #   b.	The next 6 values are unused.
    #   c.	The next (7 * num_valid) values contain the valid detections data
    #       Each group of 7 values will describe an object/box These 7 values in order.
    #       The values are:
    #         0: image_id (always 0)
    #         1: class_id (this is an index into labels)
    #         2: score (this is the probability for the class)
    #         3: box left location within image as number between 0.0 and 1.0
    #         4: box top location within image as number between 0.0 and 1.0
    #         5: box right location within image as number between 0.0 and 1.0
    #         6: box bottom location within image as number between 0.0 and 1.0

    # number of boxes returned
    num_valid_boxes = int(output[0])

    for box_index in range(num_valid_boxes):
            base_index = 7+ box_index * 7
            if (not numpy.isfinite(output[base_index]) or
                    not numpy.isfinite(output[base_index + 1]) or
                    not numpy.isfinite(output[base_index + 2]) or
                    not numpy.isfinite(output[base_index + 3]) or
                    not numpy.isfinite(output[base_index + 4]) or
                    not numpy.isfinite(output[base_index + 5]) or
                    not numpy.isfinite(output[base_index + 6])):
                # boxes with non finite (inf, nan, etc) numbers must be ignored
                continue

            x1 = max(int(output[base_index + 3] * image_to_classify.shape[0]), 0)
            y1 = max(int(output[base_index + 4] * image_to_classify.shape[1]), 0)
            x2 = min(int(output[base_index + 5] * image_to_classify.shape[0]), image_to_classify.shape[0]-1)
            y2 = min(int(output[base_index + 6] * image_to_classify.shape[1]), image_to_classify.shape[1]-1)

            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            center = (center_x, center_y)

            if (output[base_index + 1] == gesture_number):
                trajectory_queue.append(center)
                trajectory_queue.pop(0)

            # overlay boxes and labels on to the image
            overlay_on_image(image_to_classify, output[base_index:base_index + 7], trajectory_queue)



# prints usage information
def print_usage():
    print('\nusage: ')
    print('python3 run_video.py [help][resize_window=<width>x<height>]')
    print('')
    print('options:')
    print('  help - prints this message')
    print('  resize_window - resizes the GUI window to specified dimensions')
    print('                  must be formated similar to resize_window=1280x720')
    print('')
    print('Example: ')
    print('python3 run_video.py resize_window=1920x1080')


# This function is called from the entry point to do
# all the work.
def main():
    global resize_output, resize_output_width, resize_output_height
    global trajectory_queue
    global gesture_number

    gesture_number = 2
    trajectory_queue = [(0,0),(0,0),(0,0),(0,0),(0,0),(0,0),(0,0),(0,0),(0,0),(0,0)]
    x0 = [0,0,0,0,0,0,0,0,0,0]
    y0 = [0,0,0,0,0,0,0,0,0,0]

    def line(A, x, B):
        return (A * x + B)

    if (not handle_args()):
        print_usage()
        return 1

    # configure the NCS
    mvnc.SetGlobalOption(mvnc.GlobalOption.LOG_LEVEL, 2)

    # Get a list of ALL the sticks that are plugged in
    devices = mvnc.EnumerateDevices()
    if len(devices) == 0:
        print('No devices found')
        quit()

    # Pick the first stick to run the network
    device = mvnc.Device(devices[0])

    # Open the NCS
    device.OpenDevice()

    graph_filename = 'graph'

    # Load graph file to memory buffer
    with open(graph_filename, mode='rb') as f:
        graph_data = f.read()

    # allocate the Graph instance from NCAPI by passing the memory buffer
    ssd_mobilenet_graph = device.AllocateGraph(graph_data)

    # get list of all the .mp4 files in the image directory
    input_video_filename_list = os.listdir(input_video_path)
    input_video_filename_list = [i for i in input_video_filename_list if i.endswith('.mp4')]

    if (len(input_video_filename_list) < 1):
        # no images to show
        print('No video (.mp4) files found')
        return 1

    cv2.namedWindow(cv_window_name)
    cv2.moveWindow(cv_window_name, 10,  10)

    exit_app = False
    while (True):
        for input_video_file in input_video_filename_list :

            #cap = cv2.VideoCapture(input_video_file) #using videos in the folder
            cap = cv2.VideoCapture(0) #using webcam

            actual_frame_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_frame_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            print ('actual video resolution: ' + str(actual_frame_width) + ' x ' + str(actual_frame_height))

            if ((cap == None) or (not cap.isOpened())):
                print ('Could not open video device.  Make sure file exists:')
                print ('file name:' + input_video_file)
                print ('Also, if you installed python opencv via pip or pip3 you')
                print ('need to uninstall it and install from source with -D WITH_V4L=ON')
                print ('Use the provided script: install-opencv-from_source.sh')
                exit_app = True
                break

            frame_count = 0
            start_time = time.time()
            end_time = start_time
            period_start = start_time
            period_end = start_time

            while(True):
                ret, display_image = cap.read()

                if (not ret):
                    end_time = time.time()
                    print("No image from from video device, exiting")
                    break

                # check if the window is visible, this means the user hasn't closed
                # the window via the X button
                prop_val = cv2.getWindowProperty(cv_window_name, cv2.WND_PROP_ASPECT_RATIO)
                if (prop_val < 0.0):
                    end_time = time.time()
                    exit_app = True
                    break

                run_inference(display_image, ssd_mobilenet_graph, trajectory_queue, gesture_number)

                #Motion Recognition

                for point in trajectory_queue:
                    x0.append(point[0])
                    x0.pop(0)

                for point in trajectory_queue:
                    y0.append(point[1])
                    y0.pop(0)

                A1, B1 = optimize.curve_fit(line, x0, y0)[0]
                A2, B2 = optimize.curve_fit(line, y0, x0)[0]

                if ( A1 > -0.5 ):
                    if ( A1 < 0.5 ):
                        if (((y0[9] - y0[0]) ^ 2 + (x0[9] - x0[0]) ^ 2) > 70):
                            if( (x0[9] - x0[0]) < 0):
                                print('Gesture', gesture_number, 'Horizontal Move Right')
                            else:
                                print('Gesture', gesture_number, 'Horizontal Move Left')

                if ( A2 > -0.5 ):
                    if ( A2 < 0.5 ):
                        if (((y0[9] - y0[0]) ^ 2 + (x0[9] - x0[0]) ^ 2) > 60):
                            if( (y0[9] - y0[0]) < 0):
                                print('Gesture', gesture_number, 'Vertical Move Up')
                            else:
                                print('Gesture', gesture_number, 'Vertical Move Down')

                if (resize_output):
                    display_image = cv2.resize(display_image,
                                               (resize_output_width, resize_output_height),
                                               cv2.INTER_LINEAR)
                cv2.imshow(cv_window_name, display_image)

                raw_key = cv2.waitKey(1)
                if (raw_key != -1):
                    if (handle_keys(raw_key) == False):
                        end_time = time.time()
                        exit_app = True
                        break
                frame_count += 1

                if ( (frame_count % 30) == 0 ):

                    period_end = time.time()

                    real_time_frames_per_second = 30 / (period_end - period_start)
                    #print('Real Time Frames per Second: ' + str(real_time_frames_per_second))

                    period_start = period_end

            average_frames_per_second = frame_count / (end_time - start_time)
            print('Frames per Second: ' + str(average_frames_per_second))

            cap.release()

            if (exit_app):
                break;

        if (exit_app):
            break

    # Clean up the graph and the device
    ssd_mobilenet_graph.DeallocateGraph()
    device.CloseDevice()


    cv2.destroyAllWindows()


# main entry point for program. we'll call main() to do what needs to be done.
if __name__ == "__main__":
    sys.exit(main())
