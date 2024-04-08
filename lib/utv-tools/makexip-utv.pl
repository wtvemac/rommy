#!perl -w
# (C) 2003-2007 Willem Jan Hengeveld <itsme@xs4all.nl>
# Web: http://www.xs4all.nl/~itsme/
#      http://wiki.xda-developers.com/
#
# $Id$
#
use strict;
use IO::File;
use IO::Dir;
use File::stat;
use Getopt::Long;

use XdaDevelopers::CompressUtils;

use Dumpvalue;
my $d= new Dumpvalue;

sub usage {
    return <<__EOF__
Usage: makexip  <startoffset> <filesdir> <modulesdir> <outputfile>\n".
    -o FILEORDER
    -v USERSPEC
        dllfirst, dlllast
        ulRAMStart ulRAMFree, ulRAMEnd
        ulKernelFlags, ulFSRamPercent
    -3  use wince3.x compression
    -4  use wince4.x compression
    -n  FILELIST      - don't compress file list
__EOF__
}

my $compress= \&XdaDevelopers::CompressUtils::rom4compress;

my %userspec;
my %g_filepos;
my %g_nocompress;
GetOptions(
    "o=s" => sub { %g_filepos= ParseFileOrder($_[1]); },
    "n=s" => sub { %g_nocompress= ParseFileList($_[1]); },
    "v=s" => \%userspec,
    "3" => sub { $compress= \&XdaDevelopers::CompressUtils::rom3compress; },
    "4" => sub { $compress= \&XdaDevelopers::CompressUtils::rom4compress; },
) or die usage();
if (@ARGV!=4) { die usage(); }

sub ParseFileOrder {
    my $str= shift;

    my @names= split(",", $str);

    return map { (lc($names[$_]) => $_) } (0..$#names);
}
sub ParseFileList {
    return ParseFileOrder(@_);
}

# layout
# +00000   ECEC header
# +01000   module data
# +    ?   module info [ o32 + e32 structs ]
# +    ?   file data
# +    ?   modulenames
# +    ?   filenames
# +    ?   romheader
# +    ?   module entries
# +    ?   file entries

# ... if no '-n' specified, assume -o XXX == -n XXX
%g_nocompress = %g_filepos if (!scalar keys %g_nocompress);

my $startoffset= hex(shift);
my $filesdir= shift;
my $modulesdir= shift;
my $outputfile= shift;

my $files= GetFileList($filesdir);
my $modules= GetFileList($modulesdir) if (-e $modulesdir);

# ... this version does not support modules yet.
my $moduledata= PackModules($modules);
my $filedata= PackFiles($files);

my $modulenames= PackNames($modules);
my $filenames= PackNames($files);

my $rominfo= {
    moduledatasize=>length($moduledata),
    filedatasize=>length($filedata),
    modulenamessize=>length($modulenames),
    filenamessize=>length($filenames),
    loadingoffset=>$startoffset,
    nummods=>$#$modules+1,
    numfiles=>$#$files+1,

    map { ( $_ => eval($userspec{$_}) ) } keys %userspec
};
MakeRomInfo($rominfo);
MakeModuleEntries($rominfo, $modules);
MakeFileEntries($rominfo, $files);
my $romhdr= MakeRomHeader($rominfo, $modules, $files);

my $signature= MakeSignature($rominfo);

my $fh= IO::File->new($outputfile, "w+") or die "$outputfile: $!\n";
binmode $fh;
$fh->print($signature);
$fh->print($moduledata);
$fh->print($filedata);
$fh->print($modulenames);
$fh->print($filenames);
$fh->print($romhdr);
$fh->close();

printf("write xip block %08lx-%08lx, with %d files, %d modules, list: %08lx\n", 
    $rominfo->{physfirst}, $rominfo->{physlast}, 
    scalar @$files, scalar @$modules, $rominfo->{physlast}- $rominfo->{numfiles}*7*4);

exit(0);
sub MakeSignature {
    my ($rominfo)= @_;
    my $signature= ("\0" x 64) . "ECEC" . pack("V", $rominfo->{romheaderoffset}) . ("\0" x (4096-64-8));
    return $signature;
}
sub MakeRomInfo {
    my ($rominfo)= @_;
    $rominfo->{dllfirst} ||= 0;   # 0 : don't reserve memory
    $rominfo->{dlllast}  ||= 0;
    
    $rominfo->{physfirst}=$rominfo->{loadingoffset};

    $rominfo->{romheaderoffset}= $rominfo->{loadingoffset}+0x1000+$rominfo->{moduledatasize}+$rominfo->{filedatasize}+$rominfo->{modulenamessize}+$rominfo->{filenamessize};

    $rominfo->{physlast}=$rominfo->{romheaderoffset}+$rominfo->{nummods}*8*4 + $rominfo->{numfiles}*7*4 + 21*4;
    
    $rominfo->{ulRAMStart} ||= 0x8c0b0000;
    $rominfo->{ulRAMFree}  ||= 0x8c0b0000;
    $rominfo->{ulRAMEnd}   ||= 0x8c0b0000;
    
    $rominfo->{ulCopyEntries}=0;
    $rominfo->{ulCopyOffset}=0;    # ??? why did i put $rominfo->{physlast} here before?
    
    $rominfo->{ulProfileLen}=0;
    $rominfo->{ulProfileOffset}=0;
    
    $rominfo->{ulKernelFlags} ||= 0;   # often this is 2, - not-all-kmode : KFLAG_NOTALLKMODE
    
    $rominfo->{ulFSRamPercent} ||= 0x80808080;
    
    $rominfo->{ulDrivglobStart}=0;
    $rominfo->{ulDrivglobLen}=0;
    
    $rominfo->{usCPUType}= 0x1c0;  # arm
    $rominfo->{usMiscFlags}=0;
    
    # pointer to location after header+toc entries
    $rominfo->{pExtensions}=0;
    
    $rominfo->{ulTrackingStart}=0;
    
    $rominfo->{ulTrackingLen}=0;
}
sub MakeRomHeader {
    my ($rominfo, $modlist, $filelist)= @_;
    my $hdr= pack("V17v2V3", 
        $rominfo->{dllfirst},        $rominfo->{dlllast},         
        $rominfo->{physfirst},       $rominfo->{physlast},        
        $rominfo->{nummods},         
        $rominfo->{ulRAMStart},      $rominfo->{ulRAMFree},       $rominfo->{ulRAMEnd},        
        $rominfo->{ulCopyEntries},   $rominfo->{ulCopyOffset},    
        $rominfo->{ulProfileLen},    $rominfo->{ulProfileOffset}, 
        $rominfo->{numfiles},        
        $rominfo->{ulKernelFlags},   
        $rominfo->{ulFSRamPercent},  
        $rominfo->{ulDrivglobStart},  $rominfo->{ulDrivglobLen},    
        $rominfo->{usCPUType},        $rominfo->{usMiscFlags},      
        $rominfo->{pExtensions},	  
        $rominfo->{ulTrackingStart},  
        $rominfo->{ulTrackingLen},    
    );

    my @modentries;
    for my $modidx (0..$rominfo->{nummods}-1) {
        my $modinfo= $modlist->[$modidx];
        push @modentries, pack("LLLLLLLL", 
            $modinfo->{dwFileAttributes},
            $modinfo->{ftTime}{low},
            $modinfo->{ftTime}{high},
            $modinfo->{nFileSize},
            $modinfo->{lpszFileName},
            $modinfo->{ulE32Offset},       
            $modinfo->{ulO32Offset},       
            $modinfo->{ulLoadOffset},      
        );
    }
    my @filentries;
    for my $filidx (0..$rominfo->{numfiles}-1) {
        my $fileinfo= $filelist->[$filidx];
        push @filentries, pack("LLLLLLL", 
            $fileinfo->{dwFileAttributes},
            $fileinfo->{ftTime}{low},
            $fileinfo->{ftTime}{high},
            $fileinfo->{nRealFileSize},
            $fileinfo->{nCompFileSize},
            $fileinfo->{lpszFileName},
            $fileinfo->{ulLoadOffset},     
        );
    }

    return join "", $hdr, @modentries, @filentries;
}

sub GetFileList {
    my ($filedir)= @_;

    return [] unless ($filedir);

    opendir(DIR, $filedir) or warn "$!: reading $filedir\n";
    my @files= readdir DIR;
    closedir DIR;

    my @fileinfo;
    for (sort { filepos($a)<=>filepos($b) || lc($a) cmp lc($b) } @files) {
        my $path= "$filedir/$_";
        next unless -f $path;
        my $stat= stat($path);
        push @fileinfo, {
            name=>$_,
            path=>$path,
            size=>$stat->size,
            modified=>$stat->mtime,
            created=>$stat->ctime,
            accessed=>$stat->atime,
        };
    }

    return \@fileinfo;
}
sub filepos {
    my $name= shift;
    if (exists $g_filepos{lc($name)}) {
        return $g_filepos{lc($name)};
    }
    else {
        return scalar keys %g_filepos;
    }
}
# todo: implement this.
sub PackModules {
    return "";
}
sub may_compress_file {
    my ($path)= @_;

    $path =~ s/.*\///;

    return !exists $g_nocompress{lc($path)};
}
sub PackFiles {
    my ($files)= @_;

    my $filedata="";

    for (@$files) {
        $_->{filedataoffset}= length($filedata);
        my $fh= IO::File->new($_->{path}, "r") or die "$_->{path}: $!\n";
        binmode $fh;
        my $data;
        $fh->read($data, $_->{size});

        my $compressed= $compress->($data) if (may_compress_file($_->{path}));

        if (defined $compressed && length($compressed)<length($data)) {
            $filedata .= $compressed;
            $_->{storedsize}= length($compressed);
        }
        else {
            $filedata .= $data;
            $_->{storedsize}= length($data);
        }

        # alignment
        if (length($filedata)&3) {
            $filedata .= "\0" x (4-(length($filedata)&3));
        }
    }
    return $filedata;
}

sub PackNames {
    my ($files)= @_;
    
    my $namedata="";
    for (@$files) {
        $_->{nameoffset}= length($namedata);
        $namedata .= $_->{name};
        $namedata .= "\0";
        my $namelen= length($_->{name})+1;
        if ($namelen&3) {
            $namedata .= "\0" x (4-($namelen&3));
        }
    }
    return $namedata;
}

sub MakeModuleEntries {
    my ($rominfo, $modules)=@_;
    for (@$modules) {
        $_->{dwFileAttributes}= 1;  # readonly
        $_->{ftTime}=   MakeFILETIME($_->{created});
        $_->{nFileSize}=    $_->{size};
        $_->{lpszFileName}=  $rominfo->{loadingoffset}+0x1000+$rominfo->{moduledatasize}+$rominfo->{filedatasize}+$_->{nameoffset};
        $_->{ulE32Offset}=    0; # todo
        $_->{ulO32Offset}=    0; # todo
        $_->{ulLoadOffset}=   0; # todo
    }
}
sub MakeFileEntries {
    my ($rominfo, $files)=@_;
    for (@$files) {
        $_->{dwFileAttributes}= 1 | ($_->{size}>$_->{storedsize} ? 0x800 : 0);  # readonly + optional compressed
        $_->{ftTime}=   MakeFILETIME($_->{created});
        $_->{nRealFileSize}=    $_->{size};
        $_->{nCompFileSize}=    $_->{storedsize};
        $_->{lpszFileName}=  $rominfo->{loadingoffset}+0x1000+$rominfo->{moduledatasize}+$rominfo->{filedatasize}+$rominfo->{modulenamessize}+$_->{nameoffset};
        $_->{ulLoadOffset}=   $rominfo->{loadingoffset}+0x1000+$rominfo->{moduledatasize} + $_->{filedataoffset};
    }
}

sub MakeFILETIME {
    my ($seconds)= @_;

    my $win32ft= 10000000*($seconds+11644473600);

    my $high= int($win32ft/2**32);
    my $low= $win32ft- 2**32 * $high;
    return {
        high=>$high,
        low=>$low,
    };
}
