#
# frontend.py
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import silvereye
from constants import *
from product import *
from flags import flags
import isys
import iutil
import os
import re
import shutil
import types
import urlgrabber
from kickstart import AnacondaKSScript

import gettext
_ = lambda x: gettext.ldgettext("anaconda", x)

class ImageProgress(object):
    def __init__(self, progressWindow, status):
        self.progressWindow = progressWindow
        self.status = status
        self.data = ''

def imageProgress(data, callback_data=None):
    if not callback_data:
        return

    callback_data.data += data
    lines = callback_data.data.split('\n')

    m = re.match('.*Installing:\s+(\S+)\s+.*\[\s*(\d+)/(\d+)\].*', lines[-1])
    if not m:
        if len(lines) == 1:
            return
        m = re.match('.*Installing:\s+(\S+)\s+.*\[\s*(\d+)/(\d+)\].*', lines[-2])
        if not m:
            # TODO: Report other progress than just package installs
            return

    (pkg, cur, tot) = m.groups()[0:3]
    callback_data.progressWindow.set(100 * int(cur) / int(tot))
    if callback_data.status is not None:
        callback_data.status.set_text('Installing %s (%s of %s)' % (pkg, cur, tot))

class InstallClass(silvereye.InstallClass):
    # name has underscore used for mnemonics, strip if you dont need it
    id = "silvereyefrontendparent"
    name = N_("Silvereye Eucalyptus Front End Installer Parent")
    _description = N_("The default installation of %s is a 'Cloud in a Box'"
                      "install. You can optionally select a different set of"
                      "software now.")
    _descriptionFields = (productName,)
    sortPriority = 10999

    hidden = 1

    bootloaderTimeoutDefault = 5
    bootloaderExtraArgs = ["crashkernel=auto"]

    tasks = [(N_("Eucalyptus Front-end Only"),
              ["core", "eucalyptus-cloud-controller",
               "eucalyptus-storage-controller", "eucalyptus-walrus",
               "eucalyptus-cluster-controller"]),
              ]
 
    def setGroupSelection(self, anaconda):
        silvereye.InstallClass.setGroupSelection(self, anaconda)
        map(lambda x: anaconda.backend.selectGroup(x),
                      ["core", "eucalyptus-cloud-controller",
                       'X Window System', 'Desktop', 'Fonts'])
        anaconda.backend.selectPackage("eucalyptus-sc")
        anaconda.backend.selectPackage("eucalyptus-walrus")
        anaconda.backend.selectPackage("eucalyptus-cc")
        anaconda.backend.selectPackage("eucalyptus-load-balancer-image")
        anaconda.backend.selectPackage("unzip")
        anaconda.backend.selectPackage("livecd-tools")
        anaconda.backend.selectPackage("firefox")
        anaconda.backend.selectPackage("nagios")

        # Sigh, I guess we can't have nice things like wireless NICs
        # https://eucalyptus.atlassian.net/browse/INST-124
        anaconda.backend.deselectPackage("NetworkManager")
        anaconda.backend.deselectPackage("NetworkManager-gnome")

        # For 3.2 and later
        anaconda.backend.selectPackage("eucalyptus-console")

    def setInstallData(self, anaconda):
        silvereye.InstallClass.setInstallData(self, anaconda)
        anaconda.id.firewall.portlist.extend([ '53:tcp',
                                               '53:udp',
                                               '67:udp',
                                               '3260:tcp',
                                               '8443:tcp',
                                               '8772:tcp',
                                               '8773:tcp',
                                               '8774:tcp',
                                               '8888:tcp'])

        if flags.cmdline.has_key("eucaconf"):
            try:
                f = urlgrabber.urlopen(flags.cmdline["eucaconf"])
                eucaconf = open('/tmp/eucalyptus.conf', 'w')
                eucaconf.write(f.read())
                f.close()
                eucaconf.close()
            except urlgrabber.grabber.URLGrabError as e:
                if anaconda.intf:
                    rc = anaconda.intf.messageWindow( _("Warning! eucalyptus.conf download failed"),
                                                      _("The following error was encountered while"
                                                        " downloading the eucalyptus.conf file:\n\n%s" % e),
                                   type="custom", custom_icon="warning",
                                   custom_buttons=[_("_Exit"), _("_Install anyway")])
                    if not rc:
                        sys.exit(0)
                else:
                    sys.exit(0)
        else:
            pass

    def setSteps(self, anaconda):
        silvereye.InstallClass.setSteps(self, anaconda)
        if anaconda.id.displayMode == 'g':
          from gui import stepToClass
          stepToClass["frontend"] = ("frontend_gui", "FrontendInstallWindow")
        else:
          from text import stepToClasses
          stepToClasses["frontend"] = ("frontend_text", "FrontendInstallWindow")

        if not anaconda.isKickstart or not os.path.exists('/tmp/eucalyptus.conf'):
            anaconda.dispatch.skipStep("frontend", skip = 0)

    def postAction(self, anaconda):
        silvereye.InstallClass.postAction(self, anaconda)
        # XXX: use proper constants for path names
        def copy_script(src, dest, mode=0770):
            shutil.copyfile('/tmp/updates/scripts/%s' % src,
                            '%s%s' % (anaconda.rootPath, dest))
            os.chmod('%s%s' % (anaconda.rootPath, dest), mode)

        def copy_file(src, dest):
            copy_script(src, dest, mode=0644)

        copy_script('eucalyptus-frontend-config.sh',
                    '/usr/local/sbin/eucalyptus-frontend-config')
        copy_script('eucalyptus-teardown',
                    '/usr/local/sbin/eucalyptus-teardown')
        copy_script('install-unpacked-image.py',
                    '/usr/local/sbin/install-unpacked-image.py')
        copy_script('eucalyptus-setup.init',
                    '/etc/init.d/eucalyptus-setup')
        copy_script('register_cloud_start',
                    '/usr/local/sbin/register_cloud_start', mode=0755)

        os.mkdir('%s/tmp/img' % anaconda.rootPath)
        # EKI
        shutil.copyfile('/tmp/updates/scripts/vmlinuz-kexec',
                        '%s/tmp/img/vmlinuz-kexec' % anaconda.rootPath)

        # ERI
        shutil.copyfile('/tmp/updates/scripts/initramfs-kexec',
                        '%s/tmp/img/initramfs-kexec' % anaconda.rootPath)

        # Image kickstart
        newks = open('%s/tmp/ks-centos6.cfg' % anaconda.rootPath, 'w')
        ayum = anaconda.backend.ayum

        for repo in ayum.repos.listEnabled():
            newks.write('repo --name=%s --baseurl=%s\n' % (repo.name, repo.baseurl[0]))
        for line in open('/tmp/updates/ks-centos6.cfg', 'r').readlines():
            if line.startswith('repo '):
                continue
            newks.write(line)
        newks.close()

        # Image creation script
        copy_script('ami_creator.py', '/tmp/ami_creator.py')

        # XXX clean this up
        bindmount = False
        if ayum._baseRepoURL and ayum._baseRepoURL.startswith("file://"):
            os.mkdir('/mnt/sysimage/mnt/source')
            isys.mount('/mnt/source', '/mnt/sysimage/mnt/source', bindMount=True)
            bindmount = True

        # eucalyptus.conf fragment from config screen
        w = anaconda.intf.progressWindow(_("Creating EMI"), 
                                     _("Creating an initial CentOS 6 EMI."), 100)
        shutil.copyfile('/tmp/eucalyptus.conf',
                        '%s/etc/eucalyptus/eucalyptus.conf.anaconda' % anaconda.rootPath)
        copy_script('eucalyptus-firstboot-final.py',
                    '/usr/share/firstboot/modules/eucalyptus-firstboot-final.py')

        postscriptlines ="""
/usr/sbin/euca_conf --upgrade-conf /etc/eucalyptus/eucalyptus.conf.anaconda
chkconfig dnsmasq off
chkconfig eucalyptus-cloud off
chkconfig eucalyptus-setup on
"""
        postscript = AnacondaKSScript(postscriptlines,
                                      inChroot=True,
                                      logfile='/root/frontend-ks-post.log',
                                      type=KS_SCRIPT_POST)
        postscript.run(anaconda.rootPath, flags.serial, anaconda.intf)

        # TODO: Add status line for text mode
        pkgstatus = None
        if anaconda.id.displayMode == 'g':
            import gtk
            pkgstatus = gtk.Label("Preparing to install...")
            w.window.child.add(pkgstatus)
            pkgstatus.show()

        messages = '/root/ami-creation.log'
        rc = iutil.execWithCallback('/bin/sh' , ['-c', 'cd /tmp/img; /tmp/ami_creator.py -c /tmp/ks-centos6.cfg'],
                                    stdin = messages, stdout = messages, stderr = messages,
                                    root = '/mnt/sysimage', callback=imageProgress, 
                                    callback_data=ImageProgress(w, pkgstatus))

        if bindmount:
            isys.umount('/mnt/sysimage/mnt/source')
        w.pop()

    def __init__(self):
        silvereye.InstallClass.__init__(self)
