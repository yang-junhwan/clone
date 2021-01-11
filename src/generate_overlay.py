import cv2
import numpy as np
import copy
from image_registration import chi2_shift, cross_correlation_shifts


def generate_overlay(video_frames, width, height, fps, outputPath):
    print('Saving overlay result to', outputPath)
    frame_lists = sorted(video_frames, key=len, reverse=True)

    balls_in_curves = [[] for i in range(len(frame_lists))]
    codec = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(outputPath, codec, fps / 2, (width, height))
    shifts = {}

    for idx, base_frame in enumerate(frame_lists[0]):
        # Overlay frames
        bg_frame = base_frame.frame
        for list_idx, frameList in enumerate(frame_lists[1:]):
            if(idx < len(frameList)):
                overlay_frame = frameList[idx]
            else:
                overlay_frame = frameList[len(frameList) - 1]

            alpha = 1.0 / (list_idx + 2)
            beta = 1.0 - alpha
            corrected_frame = image_registration(bg_frame, overlay_frame, shifts, list_idx, width, height)
            bg_frame = cv2.addWeighted(corrected_frame, alpha, bg_frame, beta, 0)

            # Prepare balls to draw
            if(overlay_frame.ball_in_frame):
                balls_in_curves[list_idx+1].append([overlay_frame.ball[0], overlay_frame.ball[1], overlay_frame.ball_color])
        if(base_frame.ball_in_frame):
            balls_in_curves[0].append([base_frame.ball[0], base_frame.ball[1], base_frame.ball_color])

        # Draw transparent curve and non-transparent balls
        for trajectory in balls_in_curves:
            bg_frame = draw_ball_curve(bg_frame, trajectory)

        result_frame = cv2.cvtColor(bg_frame, cv2.COLOR_RGB2BGR)
        cv2.imshow('result_frame', result_frame)
        out.write(result_frame)
        if cv2.waitKey(60) & 0xFF == ord('q'):
            break


def image_registration(ref_image, offset_image, shifts, list_idx, width, height):
    if(list_idx not in shifts):
        xoff, yoff = cross_correlation_shifts(
            ref_image[:, :, 0], offset_image.frame[:, :, 0])
        shifts[list_idx] = (xoff, yoff)
    else:
        xoff, yoff = shifts[list_idx]

    offset_image.ball = tuple([offset_image.ball[0] - int(xoff), offset_image.ball[1] - int(yoff)])
    matrix = np.float32([[1, 0, -xoff], [0, 1, -yoff]])
    corrected_image = cv2.warpAffine(offset_image.frame, matrix, (width, height))

    return corrected_image


def draw_ball_curve(frame, trajectory):
    trajectory_weight = 0.75
    temp_frame = frame.copy()

    if(len(trajectory)):
        ball_points = copy.deepcopy(trajectory)
        for point in ball_points:
            clr = point[2]
            del point[2]
        ball_points = np.array(ball_points, dtype='int32')
        cv2.polylines(temp_frame, [ball_points], False, clr, 22, lineType=cv2.LINE_AA)
        frame = cv2.addWeighted(temp_frame, trajectory_weight, frame, 1-trajectory_weight, 0)

        last_ball = tuple(trajectory[-1][:-1])
        cv2.circle(frame, tuple(last_ball), 13, (255, 255, 255), -1)
    return frame