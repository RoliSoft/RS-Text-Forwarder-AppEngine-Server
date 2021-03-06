# RS Text Forwarder

This is the server-side code written in Python and designed to run on an AppEngine instance. However, the latter can be changed with minimal modification by replacing the AppEngine-specific libraries to their alternatives.

## Installation

1. Create a new AppEngine instance. Good luck finding a name that's not taken.
2. Enable Google Cloud Messaging and request a server key.
3. Checkout this repository.
4. Configure the global variables at the top of the file, most importantly `APPID` and `GCMKEY`.
4. Download AppEngine Python SDK, if you don't already have it.
5. Upload the application by issuing:

        appcfg.py -e <your-email> --passin update .

If you plan to modify the code, you may automate the upload process with a batch file, so you won't have to continuously enter your password:

    @echo off
    echo <your-app-specific-pass> | C:\Python27\python.exe C:\PROGRA~2\Google\google_appengine\appcfg.py -e <your-email> --passin update .

## Usage

Check out the repository of the client-side Android application for full documentation on all supported commands and how to use them.

List of server-side commands supported in the current commit:

### /help [server*|device]

The server or device replies with the list of commands it supports including some minimal explanation of what they do. The device reply may take up to 2 minutes to complete if your device is in deep sleep. The default parameter is the server's response.

### /ping

Pushes a ping notification through GCM to the device and when the device receives it, it invokes the `PingbackHandler` on the AppEngine, returning the original timestamp.

### /send *name*: *message*

Sends a text message to *name*. The name parameter can be of any length and contain any characters, except `:`, which is the name/text separator. Spaces around the separator will be trimmed. The message can contain further `:` characters without any issues.

To find out how the name parameter works, refer to `/chat`.

### /chat *name*

Opens a new chat window dedicated to *name*. Anything sent to that window will be forwarded as an SMS, with the exception of commands. (Anything that starts with `/`.)

Check out the client's documentation on how the name parameter is handled.

### /.*

Anything else is pushed to the device through GCM. You can disable this behaviour by setting `FWDCMD` to `False`, however you will lose quite a few important commands this way. On the upside, you can reduce the number of GCM pushes to absolutely minimal, but only do this if your data plan *really* sucks.

## Security

Upon pairing the device with the server, the device generates a 1024-bit RSA key and sends the public key to the server. A user-associated counter is also set to zero on the server side.

When sending a message, the device will sign the request with its private key and increase the counter. The server checks the signature with the public key and that the counter is higher than in the previous request. This eliminates impersonations and replay attacks.

Encryption is not currently implemented due to the fact that all the connections are SSL-encrypted between the device and server. However, if you roll your own server without SSL, or don't trust SSL, you can quickly implement an encryption that encrypts the sensitive form variables using the RSA key. (However, it is generally not a good idea to encrypt directly with the RSA key. You should instead generate a random 256-bit key for AES and use that for encryption, then communicate this key to the device by encrypting it with the public RSA key. This is also how SSL works.)

Beware, the `AppEngine server` -> `Google's XMPP server` -> `your provider's XMPP server` -> `your client` route and vice versa is not encrypted, and there might be nothing you can do about it. But then again, you shouldn't be sharing sensitive information through SMS to begin with...

## License

Both the server-side and client-side applications are licensed under [AGPLv3](http://en.wikipedia.org/wiki/Affero_General_Public_License). Consult the `LICENSE` file for more information.

tl;dr: The Affero GPL v3:

- closes the 'ASP loophole' by mandating the delivery of source code by service providers
- ensures that modified versions of the code it covers remain free and open source

If you'd like to use the code without attribution and under a different license that isn't reciprocal and doesn't address the application service provider loophole, contact me via email for further information.