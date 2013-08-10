import webapp2
import logging
import urllib
import json
import re
import unicodedata
import time

from google.appengine.api import urlfetch
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext.webapp import xmpp_handlers

class User(db.Model):
	email = db.StringProperty()
	regid = db.StringProperty()
	lastjid = db.StringProperty()
	presence = db.StringProperty(choices=set(['unknown', 'available', 'unavailable']))
	
	@property
	def gacc(self):
		return self.key().name()

class MainHandler(webapp2.RequestHandler):
	def get(self):
		self.response.write('This is an XMPP/SMS forwarder service for Android. It is being developed. Stay tuned.')

class SendHandler(webapp2.RequestHandler):
	def post(self):
		gacc = self.request.get('gacc')
		sender = self.request.get('from')
		body = self.request.get('body').encode('utf-8')
		to = gacc
		err = None
		
		user = User.get_by_key_name(gacc)
		if user is None:
			self.response.write(json.dumps({"res":"err","err":"Unknown user."}))
			return
		
		if not user.lastjid:
			to = user.email
		else:
			to = user.lastjid
		
		if not sender:
			src = 'rstxtfwd@appspot.com'
		else:
			src = re.sub("(^\.+|(?<=\.)\.+|\.+$)", "", re.sub("[^a-z0-9]", ".", unicodedata.normalize('NFKD', sender.lower()).encode('ascii', 'ignore').lower()))
			src = '%s@rstxtfwd.appspotchat.com' % (src)
		
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
		gacc = self.request.get('gacc')
		email = self.request.get('email')
		regid = self.request.get('regid')
		
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
		gacc = self.request.get('gacc')
		then = float(self.request.get('time'))
		to = gacc
		
		user = User.get_by_key_name(gacc)
		if user is None:
			self.response.write(json.dumps({"res":"err","err":"Unknown user."}))
			return
		
		if not user.lastjid:
			to = user.email
		else:
			to = user.lastjid
		
		now = time.time()
		diff = now - then
		
		logging.info('Pingback received from %s\'s device after %.7f seconds.' % (gacc, diff))		
		xmpp.send_message(to, 'Pingback received from device after %.3f seconds.' % (diff), 'rstxtfwd@appspot.com')
		self.response.write(json.dumps({"res":"ok"}))

class ErrorHandler(webapp2.RequestHandler):
	def post(self):
		sender = self.request.get('from')
		stanza = self.request.get('stanza')
		logging.error('Error received from %s: %s' % (sender, stanza))

class PresenceHandler(webapp2.RequestHandler):
	def post(self, status):
		sender = self.request.get('from')
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
			user.lastjid = sender
			user.status = status
			user.put()
		except Exception, err:
			logging.error('Unable to save lastjid=%s && status=%s for user %s: %s' % (sender, stauts, gacc, str(err)))

class XmppHandler(xmpp_handlers.CommandHandler):
	def help_command(self, message=None):
		message.reply('List of supported commands:\n/ping — Pings your device.\n/contact [name] — Searches for the specified contact and lists all matches with phone numbers.\n/send [name]: [text] — Sends the specified text to the specified contact. In case of multiple matches for the name parameter, you will receive an error.\n/chat [name] — Opens a new session in your Jabber/Talk client from [name]@rstxtfwd.appspotchat.com, and any message entered here will be sent directly to this contact.\n/locate — Sends the last-known network and GPS coordinates.\nThe name parameter can be a partial or full name or phone number. In case multiple phone numbers are associated to the same contact, you can append /N to the parameter where N is the index of the phone number as listed by /contact.')
	
	def ping_command(self, message=None):
		user = self.get_user(message.sender)
		if user is None:
			message.reply('Your XMPP address is not registered.')
			return
		elif '/' in message.sender:
			user.lastjid = message.sender
			user.status = 'available'
			user.put()
		
		message.reply('Pushing ping notification to your device...')
		if not self.send_gcm(user.regid, {'action':'ping','time':time.time()}):
			message.reply('Failed to send the push notification to your device.')
	
	def locate_command(self, message=None):
		user = self.get_user(message.sender)
		if user is None:
			message.reply('Your XMPP address is not registered.')
			return
		elif '/' in message.sender:
			user.lastjid = message.sender
			user.status = 'available'
			user.put()
		
		message.reply('Pushing location request to your device...')
		if not self.send_gcm(user.regid, {'action':'locate'}):
			message.reply('Failed to send the push notification to your device.')
	
	def send_command(self, message=None):
		user = self.get_user(message.sender)
		if user is None:
			message.reply('Your XMPP address is not registered.')
			return
		elif '/' in message.sender:
			user.lastjid = message.sender
			user.status = 'available'
			user.put()
		
		if not ':' in message.arg:
			message.reply('Invalid parameters: name/text separator was not found.')
			return
		
		contact = message.arg.split(':', 2)[0].strip()
		body = message.arg.split(':', 2)[1].strip()
		message.reply('Pushing message for %s: "%s"' % (contact, ('%s[...]' % (body[:50])) if body.__len__() > 50 else body))
		if not self.send_gcm(user.regid, {'action':'text','to':contact,'body':body,'xmback':''}):
			message.reply('Failed to send the push notification to your device.')
	
	def chat_command(self, message=None):
		user = self.get_user(message.sender)
		if user is None:
			message.reply('Your XMPP address is not registered.')
			return
		elif '/' in message.sender:
			user.lastjid = message.sender
			user.status = 'available'
			user.put()
		
		message.reply('Opening dedicated chat window with %s...' % (message.arg))
		src = re.sub("(^\.+|(?<=\.)\.+|\.+$)", "", re.sub("[^a-z0-9]", ".", unicodedata.normalize('NFKD', message.arg.lower()).encode('ascii', 'ignore').lower()))
		xmpp.send_message(message.sender, 'All messages in this window will be forwarded to %s.' % (message.arg), '%s@rstxtfwd.appspotchat.com' % (src))
	
	def unhandled_command(self, message=None):
		user = self.get_user(message.sender)
		if user is None:
			message.reply('Your XMPP address is not registered.')
			return
		elif '/' in message.sender:
			user.lastjid = message.sender
			user.status = 'available'
			user.put()
		
		message.reply('The specified command "%s" is not supported. Reply /help for the list of supported commands.' % (message.command))
	
	def text_message(self, message=None):
		user = self.get_user(message.sender)
		if user is None:
			message.reply('Your XMPP address is not registered.')
			return
		elif '/' in message.sender:
			user.lastjid = message.sender
			user.status = 'available'
			user.put()
		
		to = message.to.split('/')[0]
		if to == "rstxtfwd@appspot.com":
			message.reply('Messages not starting with a command are not supported in this context. Reply /help for the list of supported commands.')
		elif "@rstxtfwd.appspotchat.com" in to:
			contact = to.split('@')[0]
			body = message.body.strip()
			message.reply('*** Pushing message: "%s"' % (('%s[...]' % (body[:50])) if body.__len__() > 50 else body))
			if not self.send_gcm(user.regid, {'action':'text','to':contact,'body':body,'xmback':contact}):
				message.reply('Failed to send the push notification to your device.')
		else:
			message.reply('The context of this address is unknown. Please use either rstxtfwd@appspot.com or [name]@rstxtfwd.appspotchat.com.')
	
	def send_gcm(self, regid, data):
		logging.info('Pushing to device: %s' % (json.dumps(data)))
		result = urlfetch.fetch(url = 'https://android.googleapis.com/gcm/send',
			payload = json.dumps({
				'data': data,
				'registration_ids': [regid]
			}),
			method = urlfetch.POST,
			headers = {
				'Content-Type': 'application/json',
				'Authorization': 'key=AIzaSyCOEaYP9f6ck7nMvp16c9yKUROxEeWjgGU'
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
	
	def get_user(self, sender):
		return User.get_by_key_name(sender.split('/')[0])

app = webapp2.WSGIApplication([
	('/', MainHandler),
	('/send', SendHandler),
	('/register', RegistrationHandler),
	('/pingback', PingbackHandler),
	('/_ah/xmpp/message/error/', ErrorHandler),
	('/_ah/xmpp/presence/(available|unavailable)/', PresenceHandler),
	('/_ah/xmpp/message/chat/', XmppHandler),
], debug=True)
