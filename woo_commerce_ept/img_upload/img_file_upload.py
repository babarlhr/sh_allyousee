# -*- coding: utf-8 -*-
#See LICENSE file for full copyright and licensing details.

import tempfile
import base64
import requests
#from .. python_magic_0_4_11 import magic
from .. wordpress_xmlrpc import base
from .. wordpress_xmlrpc import compat
from .. wordpress_xmlrpc import media


class SpecialTransport(compat.xmlrpc_client.Transport):

    user_agent = 'Mozilla/5.0 (Windows NT 6.0) AppleWebKit/537.31 (KHTML, like Gecko) Chrome/26.0.1410.43 Safari/537.31'


def upload_image(instance,image_data,image_name,mime_type):
    if not image_data or not image_name:
        return {}    
    client = base.Client('%s/xmlrpc.php'%(instance.woo_host), instance.woo_admin_username,instance.woo_admin_password,transport=SpecialTransport())
    data = base64.decodebytes(image_data)
    # create a temporary file, and save the image
    fobj = tempfile.NamedTemporaryFile(delete=False)
    filename = fobj.name
    image=fobj.write(data)
    fobj.close()
    # mimetype=magic.from_file(filename, mime=True)
    # prepare metadata
    data = {
    'name': '%s_%s.%s'%(image_name,instance.id,mime_type.split("/")[1]),
    'type': mime_type, # mimetype
    }
    
    # read the binary file and let the XMLRPC library encode it into base64
    with open(filename, 'rb') as img:
        data['bits'] = compat.xmlrpc_client.Binary(img.read())
    
    res = client.call(media.UploadFile(data))
    
    return res

def fetch_image(image_url):
    if not image_url:
        return False
    try:
        img=requests.get(image_url,stream=True,timeout=10)
    except:
        img = False
    return img and base64.b64encode(img.content) or False