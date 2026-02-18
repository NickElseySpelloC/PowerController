# Configuration file - Email section

Use this section here you want to be emailed when there's a critical error or excessive energy use.

| Key | Description | 
|:--|:--|
| EnableEmail | Set to *True* if you want to allow the PowerController to send emails. If True, the remaining settings in this section must be configured correctly. | 
| SMTPServer | The SMTP host name that supports TLS encryption. If using a Google account, set to smtp.gmail.com |
| SMTPPort | The port number to use to connect to the SMTP server. If using a Google account, set to 587 |
| SMTPUsername | Your username used to login to the SMTP server. Alternatively, set the SMTP_USERNAME environment variable. If using a Google account, set to your Google email address. |
| SMTPPassword | The password used to login to the SMTP server. Alternatively, set the SMTP_PASSWORD environment variable. If using a Google account, create an app password for the PowerController first.  |
| SubjectPrefix | If set, the PowerController will add this text to the start of any email subject line for emails it sends. |