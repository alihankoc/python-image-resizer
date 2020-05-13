## About
Important: This script is still in development and can include bugs and sorry for typos.  :)

This python script receives messages from RabbitMQ. These messages must be in JSON format.
These messages are including the path of an image from AWS S3 and the resize options 
of it. In a message, you can specify more than one resize option. For example:
- Make a thumbnail, 
- Resize the image to a width of given width and constrain aspect ratio, 
- Stretch and crop remaining area.

After receiving the message, script resizes image for all given resize options and puts every resized image to S3 again. 
The new S3 path is added to message for every option and after all resizing is finished, 
script publishes the message that received with the resized image paths. 

You need to specify the response channel on your message. 

You can use message_format.json as message sample. 

## Security Vulnerabilities
If you discover a security vulnerability within this script, please send an e-mail to hello@alihankoc.com.tr

## License
This script is open-sourced and licensed under the [MIT license](https://opensource.org/licenses/MIT).