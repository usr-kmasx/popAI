#!/usr/bin/env python3
"""Build-time downloader with normal TLS and optional public DNS fallback.
Does not alter host networking. Used only when the configured DNS fails.
"""
import argparse
import hashlib
import json
import random
import re
import shutil
import socket
import struct
from pathlib import Path
from urllib.request import Request, urlopen


def public_lookup(name):
    identity=random.randrange(65536)
    packet=struct.pack('!6H',identity,256,1,0,0,0)+b''.join(bytes([len(p)])+p.encode() for p in name.split('.'))+b'\0'+struct.pack('!HH',1,1)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as client:
        client.settimeout(5);client.sendto(packet,('1.1.1.1',53));data=client.recv(8192)
    if struct.unpack('!H',data[:2])[0]!=identity: raise OSError('DNS identity mismatch')
    def skip(pos):
        while data[pos]:
            if data[pos]&192==192:return pos+2
            pos+=1+data[pos]
        return pos+1
    q,a=struct.unpack('!HH',data[4:8]);pos=12
    for _ in range(q):pos=skip(pos)+4
    for _ in range(a):
        pos=skip(pos);kind,_,_,size=struct.unpack('!HHIH',data[pos:pos+10]);pos+=10
        if kind==1 and size==4:return socket.inet_ntoa(data[pos:pos+4])
        pos+=size
    raise OSError('DNS did not return IPv4 for '+name)


def enable_fallback():
    original=socket.getaddrinfo
    cache={}
    def resolve(host,port,*args,**kwargs):
        try:return original(host,port,*args,**kwargs)
        except socket.gaierror:
            if host not in cache:cache[host]=public_lookup(host)
            return original(cache[host],port,*args,**kwargs)
    socket.getaddrinfo=resolve


def fetch(url, path, sha256=None, *, expected_size=None, resume=False):
    """Download and verify an asset. Optional resume keeps partial large models.

    The original destination is only published after the whole file is checked.
    Ordinary build-tool downloads keep the previous no-resume behavior.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.part')
    offset = temporary.stat().st_size if resume and temporary.is_file() else 0
    if resume and temporary.is_symlink():
        raise ValueError('Partial download must not be a symbolic link: ' + str(temporary))
    if expected_size is not None and offset > expected_size:
        raise ValueError('Partial download exceeds the expected size: ' + str(temporary))
    try:
        headers = {'Accept-Encoding': 'identity'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        with urlopen(Request(url, headers=headers), timeout=60) as response:
            if offset:
                if response.status == 206:
                    content_range = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                    if not content_range or int(content_range[1]) != offset or (
                            expected_size is not None and (
                                int(content_range[3]) != expected_size
                                or int(content_range[2]) != expected_size - 1)):
                        raise ValueError('Server returned an invalid resume range: ' + str(path))
                elif response.status == 200:
                    offset = 0  # Server does not support Range; restart the file safely.
                else:
                    raise ValueError('Server refused the resumed download: ' + str(path))
            declared = response.headers.get('Content-Length')
            if expected_size is not None and declared is not None:
                if int(declared) != expected_size - offset:
                    raise ValueError('Server reported the wrong download length: ' + str(path))
            with temporary.open('ab' if offset else 'wb') as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                output.flush()
        if expected_size is not None and temporary.stat().st_size != expected_size:
            raise ValueError('Incomplete download; rerun to resume: ' + str(path))
        with temporary.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if sha256 and digest != sha256:
            temporary.unlink(missing_ok=True)
            raise ValueError('SHA256 mismatch: ' + str(path))
        temporary.replace(path)
        print(path.name, digest, flush=True)
        return digest
    finally:
        if not resume:
            temporary.unlink(missing_ok=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('url');p.add_argument('path');p.add_argument('--sha256');p.add_argument('--size',type=int);p.add_argument('--resume',action='store_true');p.add_argument('--dns-fallback',action='store_true');a=p.parse_args()
    if a.dns_fallback:enable_fallback()
    fetch(a.url,a.path,a.sha256,expected_size=a.size,resume=a.resume)
