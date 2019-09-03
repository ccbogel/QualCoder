# This is an example PKGBUILD file. Use this as a start to creating your own,
# and remove these comments. For more information, see 'man PKGBUILD'.
# NOTE: Please fill out the license field for your package! If it is unknown,
# then please put 'unknown'.

# See http://wiki.archlinux.org/index.php/Python_Package_Guidelines for more
# information on Python packaging.

# Maintainer: Martin Ortbauer <mortbauer@gmail.com>
pkgname=Qualcoder
pkgver=1.4.0
pkgrel=1
pkgdesc=""
arch=('any')
url=""
license=('GPL')
groups=()
depends=(
    'python' 
    'python-pdfminer.six' 
    'python-chardet' 
    'python-pyqt5' 
    'python-lxml'
    'python-pikepdf'
    'python-six'
    'python-ply'
    'python-pillow'
    'vlc'
    'qpdf'
    #'python-ebooklib'
  )
makedepends=()
provides=()
conflicts=()
replaces=()
backup=()
options=(!emptydirs)
install=
source=()
md5sums=()

_gitroot=GITURL
_gitname=MODENAME

{
  cd "$srcdir"
  msg "Connecting to GIT server...."

  if [[ -d "$_gitname" ]]; then
    cd "$_gitname" && git pull origin
    msg "The local files are updated."
  else
    git clone "$_gitroot" "$_gitname"
  fi

  msg "GIT checkout done or server timeout"
  msg "Starting build..."

  rm -rf "$srcdir/$_gitname-build"
  git clone "$srcdir/$_gitname" "$srcdir/$_gitname-build"
  cd "$srcdir/$_gitname-build"

  #
  # BUILD HERE
  #
  ./autogen.sh
  ./configure --prefix=/usr
  make
}
package() {
  #cd "$srcdir/$pkgname-$pkgver"
  python setup.py install --root="$pkgdir/" --optimize=1
}

# vim:set ts=2 sw=2 et:
