import pika
import os
import time
import boto3
import json
import PIL
from PIL import Image
from resizeimage import resizeimage
from io import BytesIO

# set rabbit connection
url = os.environ.get('CLOUDAMQP_URL', 'amqp://YOUR_RABBITMQ_URL')
params = pika.URLParameters(url)
params.socket_timeout = 5
connection = pika.BlockingConnection(params)  # Connect to CloudAMQP
channel = connection.channel()  # start a channel
channel.queue_declare(queue='image_resizer', durable=True)  # Declare a queue


# stretch and crop remaining area
def fill(img, width, height):
    return resizeimage.resize_cover(img, [int(width), int(height)], validate=False)


# center the image if it is smaller than the frame, reduce it to the nearest edge if it is larger, and center it,
# fill the remaining places with the given color if it is given, or leave the transparent if not.
def center(img, width, height, background_color=(255, 255, 255, 0)):
    return resizeimage.resize_contain(img, [int(width), int(height)], Image.LANCZOS, bg_color=background_color)


# stretch without cropping
def stretch(img, width, height):
    return img.resize((int(width), int(height)), Image.ANTIALIAS)


# resize the image to a width of given width and constrain aspect ratio (auto height)
def width(img, width):
    return resizeimage.resize_width(img, int(width), validate=False)


# resize the image to a height of given height and constrain aspect ratio (auto width)
def height(img, height):
    return resizeimage.resize_height(img, int(height), validate=False)


# automatically choose the most appropriate edge to size and constrain aspect ratio.
def thumb(img, width, height):
    return resizeimage.resize_thumbnail(img, [int(width), int(height)], Image.LANCZOS)


# frame width is fixed, fit image inside, fill remaining area with the color if given, transparent if not
def fit(img, save_width, save_height, background_color=(255, 255, 255, 0)):
    width, height = img.size
    if width == height:
        return img.resize(
            (int(save_width), int(save_height)), Image.LANCZOS)
    elif width > height:
        result = Image.new(img.mode, (width, width), background_color)
        result.paste(img, (0, (width - height) // 2))
        return result.resize(
            (int(save_width), int(save_height)), Image.LANCZOS)
    else:
        result = Image.new(img.mode, (height, height), background_color)
        result.paste(img, ((height - width) // 2, 0))
        return result.resize(
            (int(save_width), int(save_height)), Image.LANCZOS)


# RESIZE IMAGE
def resize_image(bucket_name, key, action):
    s3 = boto3.resource('s3',
                        aws_access_key_id='AWS_KEY',
                        aws_secret_access_key='AWS_SECRET')
    try:
        obj = s3.Object(
            bucket_name=bucket_name,
            key=key,
        )
        obj_body = obj.get()['Body'].read()
        img = Image.open(BytesIO(obj_body))
        img = img.convert('RGB')

        # RESIZE FOR FIT OPTION
        if (action['action'] == 'fit'):
            size_split = action['size'].split('x')
            if 'color' in action:
                img = fit(img, size_split[0], size_split[1], action['color'])
            else:
                img = fit(img, size_split[0], size_split[1])
        # RESIZE FOR STRETCH OPTION
        elif(action['action'] == 'stretch'):
            size_split = action['size'].split('x')
            img = stretch(img, size_split[0], size_split[1])
        # RESIZE FOR FILL OPTION
        elif(action['action'] == 'fill'):
            size_split = action['size'].split('x')
            img = fill(img, size_split[0], size_split[1])
        # RESIZE FOR WIDTH OPTION
        elif(action['action'] == 'width'):
            img = width(img, action['size'])
        # RESIZE FOR HEIGHT OPTION
        elif(action['action'] == 'height'):
            img = height(img, action['size'])
        # RESIZE FOR CENTER OPTION
        elif(action['action'] == 'center'):
            size_split = action['size'].split('x')
            if 'color' in action:
                img = center(img, size_split[0],
                             size_split[1], action['color'])
            else:
                img = center(img, size_split[0], size_split[1])
        # RESIZE FOR THUMB OPTION
        elif(action['action'] == 'thumb'):
            size_split = action['size'].split('x')
            img = thumb(img, size_split[0], size_split[1])

        # SAVE IMAGE TO S3
        buffer = BytesIO()
        img.save(buffer, action['format'], optimize=True)
        buffer.seek(0)

        resized_key = "{size}_{prefix}.{format}".format(
            size=action['size'], prefix=action['prefix'], format=action['format'])
        obj = s3.Object(
            bucket_name=bucket_name,
            key=resized_key,
        )
        obj.put(Body=buffer, ContentType=action['mime'])

        # ADD S3 PATH TO RESPONSE MESSAGE (key is the path)
        action['key'] = resized_key

        return action
    except:
        print('Something went wrong.')
        pass

# DO SOMETHING WHEN NEW MESSAGE RECEIVED


def callback(ch, method, properties, body):
    print('New message received.')
    try:
        message_data = json.loads(body)
        # RESIZE IMAGE FOR EVERY GIVEN OPTION
        print('Start:')
        for key, action in enumerate(message_data['options']):
            message_data['options'][key] = resize_image(
                message_data['bucket_name'], message_data['key'], action)
        print('Image resized.')
        # RESIZE IMAGE FOR EVERY OPTION

        # PUBLISH MESSAGE WITH RESIZED IMAGE KEYS
        params_publish = pika.URLParameters(url)
        params_publish.socket_timeout = 5
        connection_publish = pika.BlockingConnection(
            params_publish)  # Connect to CloudAMQP
        channel_publish = connection_publish.channel()  # start a channel
        channel_publish.queue_declare(
            queue=message_data['response_channel'], durable=True)  # Declare a queue
        channel_publish.basic_publish(exchange='',
                                      routing_key=message_data['response_channel'],
                                      body=json.dumps(message_data),
                                      properties=pika.BasicProperties(
                                          delivery_mode=2,  # make message persistent
                                      ))
        connection_publish.close()
        # PUBLISH MESSAGE WITH RESIZED IMAGE KEYS

        # SEND QUEUE JOB DONE
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception:
        pass


# CHANNEL OPTIONS
channel.basic_qos(prefetch_count=1)

# REDIRECT MESSAGE TO CALLBACK FUNCTION
channel.basic_consume(queue='image_resizer', on_message_callback=callback)

# LISTEN CHANNEL
channel.start_consuming()
