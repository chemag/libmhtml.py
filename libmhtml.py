#!/usr/bin/env python
# -*- coding: iso-8859-15 -*-

# Copyright (c) 2011, Chema Gonzalez (chema@cs.berkeley.edu)
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in
#       the documentation and/or other materials provided with the.
#       distribution
#     * Neither the name of the copyright holder nor the names of its
#       contributors may be used to endorse or promote products derived
#       from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDER AND CONTRIBUTORS ``AS
# IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER AND CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
- intro
	- a python module implementing an MHTML creator/parser

- interesting functions
	- libmhtml.get(url)
	- libmhtml.parse(contents)

- usage
	- get an URL and MTHML'ize it
		> ./libmhtml.py http://www.nytimes.com /tmp/nytimes.mht
	- get an MHTML file and convert it into different files
		> mkdir /tmp/ex
		> ./libmhtml.py -p /tmp/nytimes.mht /tmp/ex/

"""

__version__ = '0.0.1';


import sys;
import os;
import re;
import getopt;
import copy;
import urlgrabber;
import urlparse;
import time;
import magic;
import quopri;
import base64;



# default values
default = {};
default['debug'] = 0;
default['operation'] = 'get';
default['base64_mime_types'] = ['image/png', 'image/x-icon'];
default['qp_mime_types'] = ['text/css', 'text/javascript'];
default['ignore_mime_types'] = ['application/rss+xml'];



def q_encode(s, enc):
	# perform quoted-printable encoding
	s = quopri.encodestring(s);
	# encode invalid characters ('?' and '_') and the space
	substitutions = {'\?': '=3F', '_': '=5F', ' ': '_'};
	for symbol, sub in substitutions.iteritems():
		pat = re.compile(symbol);
		s = pat.sub(sub, s);
	# return q-encoded title
	out = "=?%s?Q?%s?=" % (enc, s);
	return out;



def magic2mime(t):
	if 'GIF image data' in t: return 'image/gif';
	elif 'PNG image data' in t: return 'image/png';
	elif 'JPEG image data' in t: return 'image/jpeg';
	elif 'MS Windows icon resource' in t: return 'image/x-icon';
	else:
		print("Invalid magic type: \"%s\"" % t);
		sys.exit(-1);
	return '';



def add_header(subject, date, boundary):
	out = """From: <saved by libmhtml.py>
Subject: %s
Date: %s
MIME-Version: 1.0
Content-Type: multipart/related;
	boundary="%s";
	type="text/html"
""" % (subject, date, boundary);

	return out;



def add_part(ptype, boundary, content_type, url, contents):
	# add main file
	out = """\n--%s
Content-Type: %s
Content-Transfer-Encoding: %s
Content-Location: %s

""" % (boundary, content_type, ptype, url);
	if ptype == 'quoted-printable':
		out += quopri.encodestring(contents);
	elif ptype == 'base64':
		# append contents as base64
		s = base64.b64encode(contents);
		b64_text = '\n'.join(s[pos:pos+76] for pos in xrange(0, len(s), 76));
		out += b64_text;
	else:
		print("Unknown mime type: \"%s\"" % ptype);
		sys.exit(-1);
	return out;



def get_html_url(vals, url):
	if vals['debug'] > 1: print("processing %s" % (url));
	# download url
	try:
		html_code = urlgrabber.urlread(url);
	except urlgrabber.grabber.URLGrabError:
		# 404 error
		error_str = "URL down: %s" % (url);
		return (-1, error_str);
	return (0, html_code);



def get_url(vals, url):
	# get main page
	(res, main_page) = get_html_url(vals, url);
	if res < 0: return (res, main_page);

	# get title
	title_pat = '< *title *>(.*)< */ *title *>';
	title_res = re.search(title_pat, main_page, re.I);
	title = title_res.groups()[0] if title_res else '';

	# get encoding
	enc_pat = '< *meta http-equiv="Content-Type" .*charset=([^"]*)"';
	enc_res = re.search(enc_pat, main_page, re.I);
	enc = enc_res.groups()[0] if enc_res else '';

	# get interesting images/links
	img_pat = '<img src="([^"]+)"';
	img_list = re.findall(img_pat, main_page);
	img_list = list(set(img_list)); # uniq
	link_pat = '<link .*href="([^"]+)".*type="([^"]+)"';
	link_list = re.findall(link_pat, main_page);

	# add main MHTML header
	t = time.time();
	lt = time.localtime(t);
	timestamp = time.ctime(time.mktime(lt));
	boundary = "----=_NextPart_%s" % time.strftime("%Y%m%d_%H%M%S", lt);
	out = add_header(q_encode(title, enc), timestamp, boundary);

	# add main file
	content_type = 'text/html; charset="%s"' % enc;
	out += add_part('quoted-printable', boundary, content_type, url, main_page);

	# add image links
	ms = magic.open(magic.MAGIC_NONE);
	ms.load();
	for img_url in img_list:
		# ensure the url is absolute
		img_url = urlparse.urljoin(url, img_url);
		# get image file
		(res, img_contents) = get_html_url(vals, img_url);
		if res < 0:
			print("Error on %s: %s" % (img_url, img_contents));
			continue;
		# get mime type
		t = ms.buffer(img_contents);
		mime_type = magic2mime(t);
		# append image header
		out += add_part('base64', boundary, mime_type, img_url, img_contents);

	# add other links
	for link_url, mime_type in link_list:
		# ensure the url is absolute
		link_url = urlparse.urljoin(url, link_url);
		# get url file
		(res, link_contents) = get_html_url(vals, link_url);
		if res < 0:
			print("Error on %s: %s" % (link_url, link_contents));
			continue;
		if mime_type in vals['base64_mime_types']:
			# append link as base 64
			out += add_part('base64', boundary, mime_type, link_url, link_contents);
		elif mime_type in vals['qp_mime_types']:
			# append link as quoted-printable
			out += add_part('quoted-printable', boundary, mime_type, link_url, link_contents);
		elif mime_type in vals['ignore_mime_types']:
			continue;
		else:
			print("Unknown mime type: \"%s\"" % mime_type);
			sys.exit(-1);

	# finish mht file
	out += "\n--%s--\n" % boundary;
	return (0, out);



def parse_part(part):
	part = part.strip();
	# parse the part description (first three lines)
	# get Content-Type
	pat1 = 'Content-Type: (.*)';
	pat1_res = re.search(pat1, part, re.I);
	ctype = pat1_res.groups()[0].strip() if pat1_res else '';
	# get Content-Transfer-Encoding
	pat2 = 'Content-Transfer-Encoding: (.*)';
	pat2_res = re.search(pat2, part, re.I);
	cenc = pat2_res.groups()[0].strip() if pat2_res else '';
	# get Content-Location
	pat3 = 'Content-Location: (.*)';
	pat3_res = re.search(pat3, part, re.I);
	cloc = pat3_res.groups()[0].strip() if pat3_res else '';
	# check part description
	if cenc == '':
		return (-1, ctype, cenc, cloc, '');
	# parse the contents
	try:
		contents = part.split('\n\n', 1)[1];
	except:
		contents = part.split('\n\r\n', 1)[1];
	if cenc == 'base64':
		s = base64.b64decode(contents);
	elif cenc == 'quoted-printable':
		s = quopri.decodestring(contents);
	return (0, ctype, cenc, cloc, s);
	



def parse_file(vals, contents):
	# get boundary
	bnd_pat = 'boundary *= *" *([^"]*) *';
	bnd_res = re.search(bnd_pat, contents, re.I);
	bnd = bnd_res.groups()[0] if bnd_res else '';
	if bnd == '': return (-1, 'no boundary');

	# split using the boundary
	parts = contents.split('--' + bnd);

	# parse the parts
	out = [];
	for i, part in enumerate(parts):
		(res, ctype, cenc, cloc, s) = parse_part(part);
		if res == -1: continue;
		out.append([ctype, cenc, cloc, s]);

	if vals['debug'] > 1: print("%i parts" % len(out));
	return (0, out);



# \brief Get an URL as HTML
#
# \param[in] url URL to get
# \retval (error code, contents|error message)
def get_html(url):
	# use default vals
	vals = copy.deepcopy(default);
	return get_html_url(vals, url);



# \brief Get an URL and MHTML'ize it
#
# \param[in] url URL to get
# \retval (error code, contents|error message)
def get(url):
	# use default vals
	vals = copy.deepcopy(default);
	return get_url(vals, url);



# \brief Get an MHTML file and convert it into different files
#
# \param[in] contents MHTML file contents
# \retval (error code, file array|error message)
def parse(contents):
	# use default vals
	vals = copy.deepcopy(default);
	return parse_file(vals, contents);



def usage(argv):
	global default;
	print("usage: %s [opts] <url|file> <dst>" % (argv[0]));
	print("where opts can be:");
	print("\t-g: get url and mhtmlize it [default]");
	print("\t-p: parse mhtml file");
	print("\t-d: increase the debug info [default=%s]" % default['debug']);
	print("\t-h: help info");



# \brief Parse CLI options
def get_opts(argv):
	global default;

	# options
	opt_short = "hdp";
	opt_long = ["help", "debug", "parse"];

	# default values
	values = copy.deepcopy(default);

	# start parsing
	try:
		opts, args = getopt.getopt(argv[1:], opt_short, opt_long);
	except getopt.GetoptError:
		usage(argv);
		sys.exit(2);

	# parse arguments
	for opt, arg in opts:
		if opt in ("-h", "--help"):
			usage(argv);
			sys.exit();
		elif opt in ("-d", "--debug"): values['debug'] += 1;
		elif opt in ("-g", "--get"): values['operation'] = 'get';
		elif opt in ("-p", "--parse"): values['operation'] = 'parse';
		#elif opt in ("-g", "--grammar"): values['grammar'] = arg;

	remaining = args;
	return (values, remaining);



def main(argv):
	# parse options
	(vals, remaining) = get_opts(argv);
	if vals['debug'] > 1:
		for k, v in vals.iteritems(): print("vals['%s'] = %s" % (k, v));
		print("remaining args is %s" % (remaining));
	# check number of remaining arguments
	if len(remaining) < 1 or len(remaining) > 2:
		usage(argv);
		sys.exit(2);

	# get url into MHTML file
	if vals['operation'] == 'get':
		url = remaining[0];
		(res, out) = get_url(vals, url);
		if res < 0:
			print(out);
			print('----Error!');
			sys.exit(-1);
		if len(remaining) == 2:
			outfile = remaining[1];
			f = open(outfile, 'w+');
			f.write(out);
			f.close();
			if vals['debug'] > 0: print("output in %s" % (outfile));

	# parse MHTML file into its components
	elif vals['operation'] == 'parse':
		filename = remaining[0];
		try:
			f = open(filename, "r");
			contents = f.read();
			f.close();
		except:
			# error reading file
			print("Error reading file %s" % filename);
			sys.exit(-1);
		(res, out) = parse_file(vals, contents);
		if res < 0:
			print(out);
			print('----Error!');
			sys.exit(-1);
		if len(remaining) == 2:
			outdir = remaining[1];
			# dump contents
			for i in range(len(out)):
				urlname = out[i][2];
				contents = out[i][3];
				filename = os.path.basename(urlparse.urlsplit(urlname)[2]);
				if filename == '': filename = 'index.html';
				filename = os.path.join(outdir, filename);
				f = open(filename, 'w+');
				f.write(contents);
				f.close();
				if vals['debug'] > 0: print("output in %s" % (filename));
	


if ( __name__ == "__main__" ):
	# at least the CLI program name: (CLI) execution
	main(sys.argv);
else:
	# import'ed module
	# print("imported module");
	0;

