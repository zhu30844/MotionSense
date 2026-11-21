# Host counterparts of SystemLibs.cmake, for MS_PLATFORM=pcsim.
find_package(PkgConfig REQUIRED)
pkg_check_modules(ms_sqlite3  REQUIRED IMPORTED_TARGET GLOBAL sqlite3)
pkg_check_modules(ms_yaml     REQUIRED IMPORTED_TARGET GLOBAL yaml-0.1)
pkg_check_modules(ms_freetype REQUIRED IMPORTED_TARGET GLOBAL freetype2)
pkg_check_modules(ms_cjson    REQUIRED IMPORTED_TARGET GLOBAL libcjson)

add_library(sqlite3::sqlite3   ALIAS PkgConfig::ms_sqlite3)
add_library(yaml::yaml         ALIAS PkgConfig::ms_yaml)
add_library(cjson::cjson       ALIAS PkgConfig::ms_cjson)
add_library(freetype::freetype ALIAS PkgConfig::ms_freetype)

# glibc has iconv built in.
add_library(ms_iconv INTERFACE)
add_library(iconv::iconv ALIAS ms_iconv)
