import time
import tensorflow as tf
physical_devices = tf.config.experimental.list_physical_devices('GPU')
if len(physical_devices) > 0:
    tf.config.experimental.set_memory_growth(physical_devices[0], True)
from absl import app, flags, logging
from absl.flags import FLAGS
import core.utils as utils
from core.yolov4 import filter_boxes
from tensorflow.python.saved_model import tag_constants
from PIL import Image
import cv2
import numpy as np
from tensorflow.compat.v1 import ConfigProto
from tensorflow.compat.v1 import InteractiveSession
import core.config as cfg
import copy
from tracker import Tracker
from sort import *
import pickle
import os


flags.DEFINE_string('framework', 'tf', '(tf, tflite, trt')
flags.DEFINE_string('weights', './checkpoints/yolov4-416',
                    'path to weights file')
flags.DEFINE_integer('size', 416, 'resize images to')
flags.DEFINE_boolean('tiny', False, 'yolo or yolo-tiny')
flags.DEFINE_string('model', 'yolov4', 'yolov3 or yolov4')
flags.DEFINE_string('video', './data/road.mp4', 'path to input video')
flags.DEFINE_float('iou', 0.45, 'iou threshold')
flags.DEFINE_float('score', 0.25, 'score threshold')
flags.DEFINE_string('output', None, 'path to output video')
flags.DEFINE_string('output_format', 'XVID', 'codec used in VideoWriter when saving video to file')
flags.DEFINE_boolean('dis_cv2_window', False, 'disable cv2 window during the process') # this is good for the .ipynb

def getBallFrames(video_path, input_size):
    print("Video from: ", video_path)
    vid = cv2.VideoCapture(video_path)

    saved_model_loaded = tf.saved_model.load(FLAGS.weights, tags=[tag_constants.SERVING])
    infer = saved_model_loaded.signatures['serving_default']
    
    width = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH)/2)
    height = int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT)/2)
    fps = int(vid.get(cv2.CAP_PROP_FPS))
    codec = cv2.VideoWriter_fourcc(*FLAGS.output_format)
    out = cv2.VideoWriter(FLAGS.output, codec, fps, (width, height))


    width = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
    trace = np.full((int(height), int(width), 3), 255, np.uint8)
    frame_id = 0

    track_colors = [(127, 0, 127), (255, 127, 255), (127, 0, 255), (255, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 0), (0, 255, 255), (255, 0, 255), (50, 100, 150), (10, 50, 150), (120, 20, 220)]

    # Create Object Tracker
    tracker =  Sort(max_age=8, min_hits=4, iou_threshold=0.05)
    balls = []
    ball_frames=[]
    frames = []

    while True:
        return_value, frame = vid.read()
        if return_value:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame)
            frames.append(frame)
        else:
            if frame_id == vid.get(cv2.CAP_PROP_FRAME_COUNT):
                print("Video processing complete")
                break
            raise ValueError("No image! Try with another video format")
        
        frame_size = frame.shape[:2]
        image_data = cv2.resize(frame, (input_size, input_size))
        image_data = image_data / 255.
        image_data = image_data[np.newaxis, ...].astype(np.float32)
        prev_time = time.time()

        batch_data = tf.constant(image_data)
        pred_bbox = infer(batch_data)
        for key, value in pred_bbox.items():
            boxes = value[:, :, 0:4]
            pred_conf = value[:, :, 4:]

        boxes, scores, classes, valid_detections = tf.image.combined_non_max_suppression(
            boxes=tf.reshape(boxes, (tf.shape(boxes)[0], -1, 1, 4)),
            scores=tf.reshape(
                pred_conf, (tf.shape(pred_conf)[0], -1, tf.shape(pred_conf)[-1])),
            max_output_size_per_class=50,
            max_total_size=50,
            iou_threshold=FLAGS.iou,
            score_threshold=FLAGS.score
        )

        boxes = boxes.numpy()
        scores = scores.numpy()
        classes = classes.numpy()
        valid_detections = valid_detections.numpy()

        frame_h, frame_w, _ = frame.shape
        detections = []
        offset = 50
        for i in range(valid_detections[0]):
            coor = boxes[0][i]
            score = scores[0][i]
            coor[0] = (coor[0] * frame_h)
            coor[2] = (coor[2] * frame_h)
            coor[1] = (coor[1] * frame_w)
            coor[3] = (coor[3] * frame_w)
            detections.append(np.array([coor[1]-offset, coor[0]-offset, coor[3]+offset, coor[2]+offset, score]))

        if(len(detections) > 0):
            trackings = tracker.update(np.array(detections))
        else:
            trackings = tracker.update()

        for t in trackings:
            print('id', t[4])
            t = t.astype('int32') 
            t[0] = int(t[0])
            t[1] = int(t[1])
            t[2] = int(t[2])
            t[3] = int(t[3])
            start = (t[0], t[1])
            end = (t[2], t[3])
            print(start)
            cv2.rectangle(frame, start, end, (255, 0, 0), 5) 
            cv2.putText(frame, str(t[4]), start, cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 255), 2, cv2.LINE_AA)

            clr = t[4] % 12
            centerX = int((t[0] + t[2]) / 2)
            centerY = int((t[1] + t[3]) / 2)
            balls.append([centerX, centerY, t[4]])

            # cv2.circle(frame, (centerX, centerY), 15, track_colors[clr], -1)
            # cv2.circle(trace, (centerX, centerY), 15, track_colors[clr], -1)

        for ballX, ballY, ballId in balls:
            overlay = frame.copy()
            cv2.circle(overlay, (ballX, ballY), 10, track_colors[ballId % 12], -1)
            alpha = 0.75  # Transparency factor.
            frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

        if(len(trackings) > 0):
            if(len(ball_frames) == 0):
                ball_frames.extend(frames[-20:])
            ball_frames.append(frame)


        curr_time = time.time()
        exec_time = curr_time - prev_time
        result = np.asarray(image)
        info = "time: %.2f ms" %(1000*exec_time)
        print(info)

        result = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        # combined = np.concatenate((result, trace), axis=1)  
        # detection = cv2.resize((combined), (0, 0), fx=0.5, fy=0.5)
        detection = cv2.resize((result), (0, 0), fx=0.5, fy=0.5)
        cv2.imshow("result", detection)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

        out.write(detection)

        frame_id += 1

    return ball_frames

def main(_argv):
    config = ConfigProto()
    config.gpu_options.allow_growth = True
    session = InteractiveSession(config=config)
    STRIDES, ANCHORS, NUM_CLASS, XYSCALE = utils.load_config(FLAGS)
    input_size = FLAGS.size
    video_path = FLAGS.video

    videoFrames = []
    root = './videos6'

    for path in os.listdir(root):
        print(path)
        ball_frames = getBallFrames(root + '/' + path, input_size)
        videoFrames.append(ball_frames)

    with open('frames6.pkl', 'wb') as f:
        pickle.dump(videoFrames, f)

if __name__ == '__main__':
    try:
        app.run(main)
    except SystemExit:
        pass