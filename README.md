# RS Text Forwarder

This is the server-side code written in Python and designed to run on an AppEngine instance. However, the latter can be changed with minimal modification by replacing the AppEngine-specific libraries to their alternatives.

## Installation

1. Create a new AppEngine instance. Good luck finding a name that's not taken.
2. Checkout this repository.
3. Replace a few hard-coded URLs with your own.
4. Download AppEngine Python SDK, if you don't already have it.
5. Upload the application:

        appcfg.py -e <your-email> --passin update .

If you plan to modify the code, you may automate the upload process with a batch file, so you won't have to continuously enter your password:

    @echo off
    echo <your-app-specific-pass> | C:\Python27\python.exe C:\PROGRA~2\Google\google_appengine\appcfg.py -e <your-email> --passin update .

## Usage

Check out the client-side Android application. You will have to compile that yourself after a minimal modification as well.

## Security

Stronger authentication is planned, however encryption is not. Get an SSL certificate if you want to encrypt the traffic between the phone and the AppEngine server.

Beware, the `AppEngine server` -> `Google's XMPP server` -> `your provider's XMPP server` -> `your client` route and vice versa is not encrypted, and there might be nothing you can do about it. But then again, you shouldn't be sharing sensitive information through SMS to begin with...

## License

Both the server-side and client-side applications are licensed under [AGPLv3](http://en.wikipedia.org/wiki/Affero_General_Public_License). Consult the `LICENSE` file for more information.

tl;dr: The Affero GPL v3:

- closes the 'ASP loophole' by mandating the delivery of source code by service providers
- ensures that modified versions of the code it covers remain free and open source

If you'd like to use the code without attribution and under a different license that isn't reciprocal and doesn't address the application service provider loophole, contact me via email for further information.