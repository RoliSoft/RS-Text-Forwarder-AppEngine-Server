#
#  RS Text Forwarder
#  Copyright ©2013 RoliSoft <rolisoft@gmail.com>
#  
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#  
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see [http://www.gnu.org/licenses/].
#

import webapp2
import logging
import urllib
import json
import re
import unicodedata
import time
import base64

from Crypto.Hash import SHA
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from google.appengine.api import urlfetch
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext.webapp import xmpp_handlers

# Global variables that need to be configured.

APPID  = 'rstxtfwd'  # <APPID>.appspot.com
GCMKEY = ''  # key for Google Cloud Messaging
FWDCMD = True  # whether to push commands to the device that don't have server-side implementation

# Touching anything below this line voids your warranty, which you would've known you don't have in the first place if you would've read the license.

XMPUB  = '%s@appspot.com' % (APPID)
XMPRIV = '@%s.appspotchat.com' % (APPID)

# Classes for the AppEngine Datastore

class User(db.Model):
	"""
		Represents a registered user.
	"""
	
	email = db.StringProperty()
	regid = db.StringProperty()
	pubkey = db.StringProperty()
	counter = db.IntegerProperty()
	lastjid = db.StringProperty()
	presence = db.StringProperty(choices=set(['unknown', 'available', 'unavailable']))
	
	@property
	def gacc(self):
		return self.key().name()

# Request and message handler implementations

class MainHandler(webapp2.RequestHandler):
	def get(self):
		"""
			Tells users to fuck off. Once this project gets into an "okay" state,
			it'll redirect the users to the Github repositories.
		"""
		
		self.response.write('This is an XMPP/SMS forwarder service for Android. It is being developed. Stay tuned.')

class SendHandler(webapp2.RequestHandler):
	def post(self):
		"""
			Sends an XMPP message the registered address of the user.
			This is the endpoint the Android client calls to send a message via XMPP.
			Due to the funny way Google's XMPP implementation works, you may or may not get an
			immediate error message if the delivery failed. If not, it'll receive in ErrorHandler.
		"""
		
		gacc = self.request.POST['gacc']
		sender = self.request.POST['from']
		body = self.request.POST['body']
		to = gacc
		err = None
		
		user = User.get_by_key_name(gacc)
		if user is None:
			self.response.write(json.dumps({"res":"err","err":"Unknown user."}))
			return
		
		if not 'X-Signature' in self.request.headers:
			self.response.write(json.dumps({"res":"err","err":"Signature required."}))
			return
		
		xsign = self.request.headers['X-Signature'].split(' ', 2)
		counter = long(xsign[0], 36)
		temp = str(counter) + '&' + urllib.unquote(self.request.body).replace('+', ' ')
		
		hash = SHA.new(temp)
		verifier = PKCS1_v1_5.new(RSA.importKey(base64.standard_b64decode(user.pubkey)))
		signature = base64.standard_b64decode(xsign[1])
		
		if not verifier.verify(hash, signature):
			self.response.write(json.dumps({"res":"err","err":"Signature invalid."}))
			return
		
		if counter <= user.counter:
			self.response.write(json.dumps({"res":"err","err":"Counter too low."}))
			return
		else:
			user.counter = counter
			user.put()
		
		if not user.lastjid:
			to = user.email
		else:
			to = user.lastjid
		
		if not sender:
			src = XMPUB
		elif sender == XMPUB or XMPRIV in sender:
			src = sender
		else:
			src = re.sub("(^\.+|(?<=\.)\.+|\.+$)", "", re.sub("[^a-z0-9\\-_\\.]", ".", unicodedata.normalize('NFKD', sender.lower()).encode('ascii', 'ignore').lower()))
			src = src + XMPRIV
		
		if not body:
			body = '%sEmpty response received from device.' % ('*** ' if XMPRIV in sender else '')
		
		logging.info('Sending XMPP from %s to %s: %s' % (src, to, body))
		
		try:
			xmpp.send_message(to, body, src)
		except Exception, ex:
			logging.error('Error while sending previous message: %s' % (str(ex)))
			err = ex
		
		if err is None:
			self.response.write(json.dumps({"res":"ok"}))
		else:
			self.response.write(json.dumps({"res":"err","err":str(err)}))

class RegistrationHandler(webapp2.RequestHandler):
	def post(self):
		"""
			Receives a new registration with Google Account, GCM registration ID, and the preferred
			XMPP address. Old registrations for the same Google Account will be discarded.
		"""
		
		gacc = self.request.POST['gacc']
		email = self.request.POST['email']
		regid = self.request.POST['regid']
		pubkey = self.request.POST['pbkey']
		
		user = User.get_by_key_name(gacc)
		if not user is None:
			logging.warn('Removing older account of %s.' % (gacc))
			user.delete()
		
		if not email:
			email = gacc
		
		try:
			user = User(key_name=gacc)
			user.email = email
			user.regid = regid
			user.pubkey = pubkey
			user.counter = 1
			user.lastjid = email
			user.presence = 'unknown'
			user.put()
		except Exception, err:
			logging.error('Error while saving account %s: %s' % (gacc, str(err)))
			self.response.write(json.dumps({"res":"err","err":str(err)}))
			return
		
		if gacc == email:
			logging.info('Registered account %s.' % (gacc))
		else:
			logging.info('Registered account %s with forwarding to %s.' % (gacc, email))
		
		self.response.write(json.dumps({"res":"ok"}))

class PingbackHandler(webapp2.RequestHandler):
	def post(self):
		"""
			Receives a pingback with timestamp from the device.
			See ping_command in XmppHandler for the counterpart.
		"""
		
		gacc = self.request.POST['gacc']
		then = float(self.request.POST['time'])
		sender = self.request.POST['from']
		to = gacc
		
		user = User.get_by_key_name(gacc)
		if user is None:
			self.response.write(json.dumps({"res":"err","err":"Unknown user."}))
			return
		
		if not 'X-Signature' in self.request.headers:
			self.response.write(json.dumps({"res":"err","err":"Signature required."}))
			return
		
		xsign = self.request.headers['X-Signature'].split(' ', 2)
		counter = long(xsign[0], 36)
		temp = str(counter) + '&' + urllib.unquote(self.request.body).replace('+', ' ')
		
		hash = SHA.new(temp)
		verifier = PKCS1_v1_5.new(RSA.importKey(base64.standard_b64decode(user.pubkey)))
		signature = base64.standard_b64decode(xsign[1])
		
		if not verifier.verify(hash, signature):
			self.response.write(json.dumps({"res":"err","err":"Signature invalid."}))
			return
		
		if counter <= user.counter:
			self.response.write(json.dumps({"res":"err","err":"Counter too low."}))
			return
		else:
			user.counter = counter
			user.put()
		
		if not user.lastjid:
			to = user.email
		else:
			to = user.lastjid
		
		if not sender:
			src = XMPUB
		elif sender == XMPUB or XMPRIV in sender:
			src = sender
		else:
			src = re.sub("(^\.+|(?<=\.)\.+|\.+$)", "", re.sub("[^a-z0-9\\-_\\.]", ".", unicodedata.normalize('NFKD', sender.lower()).encode('ascii', 'ignore').lower()))
			src = src + XMPRIV
		
		prep = ''
		if XMPRIV in src:
			prep = '*** '
		
		now = time.time()
		diff = now - then
		
		logging.info('Pingback received from %s\'s device after %.7f seconds.' % (gacc, diff))		
		xmpp.send_message(to, '%sPingback received from device after %.3f seconds.' % (prep, diff), src)
		self.response.write(json.dumps({"res":"ok"}))

class ErrorHandler(webapp2.RequestHandler):
	def post(self):
		"""
			Receives an error message. It is most likely a bounced message.
			See the documentation for PresenceHandler on more info why this occurs.
		"""
		
		sender = self.request.get('from')
		stanza = self.request.get('stanza')
		logging.error('Error received from %s: %s' % (sender, stanza))

class PresenceHandler(webapp2.RequestHandler):
	def post(self, status):
		"""
			Receives presence status from users who have added at least one of the application's
			addresses to their friends list. GMail and GVGW will be skipped, as they're not "real clients".
			This is a very important part of the application, because it receives and saves the full JID
			of the user. Without a full JID, the messages may not be delivered properly and be bounced.
		"""
		
		sender = self.request.get('from')
		
		if status == 'probe':
			xmpp.send_presence(sender, None, self.request.get('to'), xmpp.PRESENCE_TYPE_AVAILABLE)
			status = 'available'
		
		logging.info('User %s is now %s.' % (sender, status))
		
		if '/gmail.' in sender or '/GVGW' in sender:
			loc = sender.split('/')[1]
			logging.info('Skipping setting of lastjid due to %s presence.' % (loc))
			return
		
		gacc = sender.split('/')[0]
		user = User.get_by_key_name(gacc)
		if user is None:
			logging.warn('User %s is not in database; not saving presence.' % (gacc))
			return
		
		try:
			if status == 'available':
				user.lastjid = sender
			
			user.status = status
			user.put()
		except Exception, err:
			logging.error('Unable to save lastjid=%s && status=%s for user %s: %s' % (sender, stauts, gacc, str(err)))

class XmppHandler(xmpp_handlers.CommandHandler):
	def help_command(self, message=None):
		"""
			Replies with a list of commands that are supported on the server or device,
			depending which is requested in the first parameter.
		"""
		
		user = self.get_user(message)
		if not user:
			return
			
		prep = ''
		if XMPRIV in message.to:
			prep = '*** '
		
		if message.arg == "device":
			if not FWDCMD:
				message.reply('%sThis server does not forward unhandled commands to the device.' % (prep))
			else:
				message.reply('%sPushing help request to your device...' % (prep))
				if not self.send_gcm(user.regid, {'action':'cmd','cmd':message.command,'arg':message.arg}, message.to, XMPRIV in message.to):
					message.reply('%sFailed to send the push notification to your device.' % (prep))
		else:
			message.reply('%sList of supported commands:\n/help device -- Requests the list of commands your device supports.\n/ping -- Pings your device.\n/send [name]: [text] -- Sends the specified text to the specified contact. In case of multiple matches for the name parameter, you will receive an error.\n/chat [name] -- Opens a new session in your Jabber/Talk client from [name]%s, and any message entered here will be sent directly to this contact.\nThe name parameter can be a partial or full name or phone number. In case multiple phone numbers are associated to the same contact, you can append /N to the parameter where N is the index of the phone number as listed by /contact.' % (prep, XMPRIV))
	
	def ping_command(self, message=None):
		"""
			Pushes a ping notification to the device with a timestamp. The device will return this
			timestamp once it got the notification by requesting /pingback on this server, at
			which point the user will receive a message containing the total round-trip time.
		"""
		
		user = self.get_user(message)
		if not user:
			return
		
		prep = ''
		if XMPRIV in message.to:
			prep = '*** '
		
		message.reply('%sPushing ping notification to your device...' % (prep))
		if not self.send_gcm(user.regid, {'action':'ping','time':time.time()}, message.to, XMPRIV in message.to):
			message.reply('%sFailed to send the push notification to your device.' % (prep))
	
	def send_command(self, message=None):
		"""
			Pushes a "send SMS" notification to the device forwarding the specified parameters.
		"""
		
		user = self.get_user(message)
		if not user:
			return
		
		prep = ''
		if XMPRIV in message.to:
			prep = '*** '
		
		if not ':' in message.arg:
			message.reply('%sInvalid parameters: name/text separator was not found.' % (prep))
			return
		
		contact = message.arg.split(':', 2)[0].strip()
		body = message.arg.split(':', 2)[1].strip()
		message.reply('%sPushing message for %s: "%s"' % (prep, contact, ('%s[...]' % (body[:50])) if body.__len__() > 50 else body))
		if not self.send_gcm(user.regid, {'action':'text','to':contact,'body':body}, message.to, XMPRIV in message.to):
			message.reply('%sFailed to send the push notification to your device.' % (prep))
	
	def chat_command(self, message=None):
		"""
			Opens a new session by replying from a different address dedicated to the user specified in the parameters.
			This is now handled on the client-side, therefore a push notification is required to get the
			proper address for the specified contant.
		"""
		
		user = self.get_user(message)
		if not user:
			return
		
		prep = ''
		if XMPRIV in message.to:
			prep = '*** '
		
		message.reply('%sPushing request for dedicated chat window with %s...' % (prep, message.arg))
		if not self.send_gcm(user.regid, {'action':'chat','with':message.arg}, message.to, XMPRIV in message.to):
			message.reply('%sFailed to send the push notification to your device.' % (prep))
	
	def unhandled_command(self, message=None):
		"""
			Handles a command that has no server implementation. If FWDCMD is True, it does so by pushing the command
			to the device in hopes it can do something with it. If the device couldn't handle it either, or FWDCMD is
			set to False, an error message will be sent.
		"""
		
		user = self.get_user(message)
		if not user:
			return
		
		prep = ''
		if XMPRIV in message.to:
			prep = '*** '
		
		if not FWDCMD:
			message.reply('%sThe specified command "%s" is not supported. Reply "/help server" or "/help device" for the list of supported commands.' % (prep, message.command))
			return
		
		message.reply('%sPushing command %s to device...' % (prep, message.command))
		if not self.send_gcm(user.regid, {'action':'cmd','cmd':message.command,'arg':message.arg}, message.to, XMPRIV in message.to):
			message.reply('%sFailed to send the push notification to your device.' % (prep))
	
	def text_message(self, message=None):
		"""
			Handles messages that don't start with a command.
			For messages sent to <app>@appspot.com, it replies with an error message;
			for messages sent to <name>@<app>.appspotchat.com, pushes a "send SMS" notification to the device.
		"""
		
		user = self.get_user(message)
		if not user:
			return
		
		to = message.to.split('/')[0]
		if to == XMPUB:
			message.reply('Messages not starting with a command are not supported in this context. Reply /help for the list of supported commands.')
		elif XMPRIV in to:
			contact = to.split('@')[0]
			body = message.body.strip()
			message.reply('*** Pushing message: "%s"' % (('%s[...]' % (body[:50])) if body.__len__() > 50 else body))
			if not self.send_gcm(user.regid, {'action':'text','to':contact,'body':body}, contact, True):
				message.reply('*** Failed to send the push notification to your device.')
		else:
			message.reply('The context of this address is unknown. Please use either %s or [name]%s.' % (XMPUB, XMPRIV))
	
	def send_gcm(self, regid, data, xmback=None, xmpriv=False):
		"""
			Pushes a notification to the device through Google Cloud Messaging.
		"""
		
		if not xmback is None and not XMPUB in xmback:
			data['_addr'] = xmback.split('/')[0].split(XMPRIV)[0]
		
		if xmpriv:
			data['_priv'] = True
		
		logging.info('Pushing to device: %s' % (json.dumps(data)))
		result = urlfetch.fetch(url = 'https://android.googleapis.com/gcm/send',
			payload = json.dumps({
				'data': data,
				'registration_ids': [regid]
			}),
			method = urlfetch.POST,
			headers = {
				'Content-Type': 'application/json',
				'Authorization': 'key=' + GCMKEY
			}
		)
		
		if result.status_code == 200:
			jres = json.loads(result.content)
			if jres['success'] == 0:
				logging.info('Push failed: %s' % (result.content))
				return False
			else:
				logging.info('Push result: %s' % (result.content))
				return True
		else:
			logging.info('Push failed with HTTP %i: %s' % (result.status_code, result.content))
			return False
	
	def get_user(self, message=None):
		"""
			Fetches the user from the database for the specified JID.
		"""
		
		if not message:
			return
		
		user = User.get_by_key_name(message.sender.split('/')[0])
		
		if user is None:
			message.reply('Your XMPP address is not registered.')
			return
		elif '/' in message.sender:
			user.lastjid = message.sender
			user.status = 'available'
			user.put()
		
		return user

# Routing definitions for the handlers above

app = webapp2.WSGIApplication([
	('/', MainHandler),
	('/send', SendHandler),
	('/register', RegistrationHandler),
	('/pingback', PingbackHandler),
	('/_ah/xmpp/message/error/', ErrorHandler),
	('/_ah/xmpp/presence/(available|unavailable|probe)/', PresenceHandler),
	('/_ah/xmpp/message/chat/', XmppHandler),
], debug=True)