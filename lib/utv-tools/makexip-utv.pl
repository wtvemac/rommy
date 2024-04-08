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
use List::Util qw( min );

# EMAC: I added -c to l ist compressed files. Compression happens before this so I don't have to deal with XdaDevelopers::CompressUtils
#use XdaDevelopers::CompressUtils;

# EMAC: exes and dlls will be pulled out of the filesdir for the moudles and copy entry files.

use Dumpvalue;
my $d= new Dumpvalue;

sub usage {
    return <<__EOF__
Usage: makexip  <startoffset> <filesdir> <outputfile>\n".
    -o FILEORDER
    -v USERSPEC
        dllfirst, dlllast
        ulRAMStart ulRAMFree, ulRAMEnd
        ulKernelFlags, ulFSRamPercent, usMiscFlags
    -3  use wince3.x compression
    -4  use wince4.x compression
    -c  FILELIST      - pre-compressed file list
    -n  FILELIST      - don't compress file list
__EOF__
}

my $compress= \&XdaDevelopers::CompressUtils::rom4compress;

my %userspec;
my %g_filepos;
my %g_nocompress;
my %g_precompressed;
my @romobjs = (); # EMAC: added to build rom modules and check copy sections

#EMAC: force order for the UTV.
%g_filepos=ParseFileOrder("nk.exe,coredll.dll,filesys.exe,gwes.exe,device.exe,shell.exe,toolhelp.dll,ole32.dll,schannel.dll,ndis.dll,ddcore.dll,dsound.dll,dsounds.dll,fsdmgr.dll,compressfsd.dll,releasefsd.dll,fatfs.dll,storagemgr.dll,regio.dll,logmgr.dll,L64734.dll,cadll.dll,DtvTransport.dll,MpegBuffs.dll,SoloMpeg.dll,DAVC.dll,DAVCUtils.dll,MPEGStc.dll,APG.dll,FrontPanel.dll,Macrovision.dll,CCEncode.dll,MpegFeeder.dll,MpegAudio.dll,AudioPort.dll,AnalogAVC.dll,AAMux.DLL,BT835.DLL,MAVC.DLL,DVR.DLL,PhysMem.DLL,dvrfsd.DLL,StcUtils.DLL,adt.dll,DataDl.dll,RFBypassCan.DLL,modem.dll,ceddk.dll,IIC.dll,tvpak_hal.dll,irinput.dll,keybddr.dll,solosc.dll,GPIO.dll,ddi.dll,dsndsrv.exe,iroutput.dll,ATADiskAV.dll,ohci.dll,wince.nls,initobj.dat,default.fdf,initdb.ini,tahoma8.fnt,tahoma9.fnt,tahoma10.fnt,tahoma12.fnt,tahoma14.fnt");
#%g_filepos= ParseFileOrder("nk.exe,coredll.dll,filesys.exe,device.exe,shell.exe,toolhelp.dll,ole32.dll,dsounds.dll,releasefsd.dll,DAVCUtils.dll,Macrovision.dll,AudioPort.dll,schannel.dll,storagemgr.dll,StcUtils.DLL,ndis.dll,ddcore.dll,dsound.dll,fsdmgr.dll,compressfsd.dll,regio.dll,MPEGStc.dll,fatfs.dll,logmgr.dll,L64734.dll,SoloMpeg.dll,FrontPanel.dll,CCEncode.dll,DtvTransport.dll,DAVC.dll,AnalogAVC.dll,AAMux.DLL,BT835.DLL,MAVC.DLL,adt.dll,PhysMem.DLL,dvrfsd.DLL,RFBypassCan.DLL,ceddk.dll,IIC.dll,keybddr.dll,MpegBuffs.dll,MpegFeeder.dll,DVR.DLL,GPIO.dll,DataDl.dll,modem.dll,tvpak_hal.dll,dsndsrv.exe,iroutput.dll,irinput.dll,ddi.dll,gwes.exe,solosc.dll,ATADiskAV.dll,ohci.dll,cadll.dll,APG.dll,MpegAudio.dll,wince.nls,initobj.dat,default.fdf,initdb.ini,tahoma8.fnt,tahoma9.fnt,tahoma10.fnt,tahoma12.fnt,tahoma14.fnt");

GetOptions(
    "o=s" => sub { %g_filepos= ParseFileOrder($_[1]); },
    "n=s" => sub { %g_nocompress= ParseFileList($_[1]); },
    # EMAC: added
    "c=s" => sub { %g_precompressed= ParseFileList($_[1]); },
    "v=s" => \%userspec,
    #"3" => sub { $compress= \&XdaDevelopers::CompressUtils::rom3compress; },
    #"4" => sub { $compress= \&XdaDevelopers::CompressUtils::rom4compress; },
) or die usage();
#if (@ARGV!=4) { die usage(); }
if (@ARGV!=3) { die usage(); }

# EMAC: entire sub changed for pre-compressed values
sub ParseFileOrder {
    my $str= shift;

    my @names= split(",", $str);

    my %files = ();
    my $idx = 0;
    for (@names) {
        my @values = split("=", $_);
        if(scalar(@values) > 1) {
            $files{lc($values[0])} = $values[1];
        } else {
            $files{lc($_)} = $idx;
        }

        $idx++;
    }

    return %files;
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
# EMAC: removed
#my $modulesdir= shift;
my $outputfile= shift;

my $files= GetFileList($filesdir, 0, 0);
# EMAC: add arg to scan for exes and dlls for modules.
my $modules= GetFileList($filesdir, 1, 0);
my $copyentries= GetFileList($filesdir, 0, 1);

# ... this version does not support modules yet.
my $moduledata= PackModules($startoffset, \%userspec, $modules, \@romobjs);
my $filedata= PackFiles($files);
my $copydata= PackCopyEntries($startoffset, \%userspec, $copyentries, \@romobjs);
my $modulenames= PackNames($modules);
my $filenames= PackNames($files);
my ($copylist, $potentialRAMStart, $potentialRAMFree) = PackCopyList($startoffset, length($moduledata), length($filedata), $copyentries);

my $rominfo= {
    moduledatasize=>length($moduledata),
    filedatasize=>length($filedata),
    modulenamessize=>length($modulenames),
    filenamessize=>length($filenames),
    copydatasize=>length($copydata),
    copylistsize=>length($copylist),
    loadingoffset=>$startoffset,
    nummods=>$#$modules+1,
    numfiles=>$#$files+1,
    potentialRAMStart=>$potentialRAMStart,
    potentialRAMFree=>$potentialRAMFree,
    numcopy=>$#$copyentries+1,

    map { ( $_ => eval($userspec{$_}) ) } keys %userspec
};
MakeRomInfo($rominfo);
MakeModuleEntries($rominfo, $modules);
MakeFileEntries($rominfo, $files);
my $romhdr= MakeRomHeader($rominfo, $modules, $files, $copyentries);

my $signature= MakeSignature($rominfo, $modules);

$moduledata = MakeNKROMHDRPointer($rominfo, $modules, $moduledata);

my $fh= IO::File->new($outputfile, "w+") or die "$outputfile: $!\n";
binmode $fh;
my $fsize = 0; # EMAC: added to apply file padding for the UTV
$fh->print($signature); $fsize += length($signature);
$fh->print($moduledata); $fsize += length($moduledata);
$fh->print($filedata); $fsize += length($filedata);
$fh->print($copydata); $fsize += length($copydata);
$fh->print($modulenames); $fsize += length($modulenames);
$fh->print($filenames); $fsize += length($filenames);
$fh->print($copylist); $fsize += length($copylist);
$fh->print($romhdr); $fsize += length($romhdr);


$fh->print("\x00" x 0x1FE00);

$fh->close();

printf("write xip block 0x%08lx-0x%08lx, with %d files, %d modules, %d copy entries, list: 0x%08lx\n", 
    $rominfo->{physfirst}, $rominfo->{physlast}, 
    scalar @$files, scalar @$modules, scalar @$copyentries, $rominfo->{physlast}- $rominfo->{numfiles}*7*4);

exit(0);

# EMAC: UTV has the ROMHDR pointer in the nk.exe file
sub FindNKROMHDRPointer {
    my ($moduledata, $checkstr, $startoff, $size)=@_;

    for(my $ofs=$startoff; $ofs < min(($startoff + $size), length($moduledata)); $ofs+=4)
    {
        my $againststr = substr($moduledata, $ofs, length($checkstr));
        if ($checkstr eq $againststr) {
            return $ofs;
        }
    }

    return -1;
}
sub MakeNKROMHDRPointer {
    my ($rominfo, $modules, $moduledata)=@_;

    if(defined($rominfo->{prevROMHDRAddy}) and $rominfo->{prevROMHDRAddy} > 0) {
        my $prevROMHDRAddy = pack("V", $rominfo->{prevROMHDRAddy});

        for (@$modules) {
            if($_->{name}=~/^nk.exe$/i) {
                my $hdrptroff = -1;

                if($hdrptroff == -1) {
                    $hdrptroff = FindNKROMHDRPointer($moduledata, $prevROMHDRAddy . "\x00\x00\x00\x00\x20\x00\x20\x00", $_->{moduledataoffset}, $_->{size});
                }
                if($hdrptroff == -1) {
                    $hdrptroff = FindNKROMHDRPointer($moduledata, $prevROMHDRAddy . "\x00\x00\x00\x00\x20\x00\x20\x00", $_->{moduledataoffset}, $_->{size});
                }
                if($hdrptroff == -1) {
                    $hdrptroff = FindNKROMHDRPointer($moduledata, $prevROMHDRAddy . "\x0a\x00\x0d\x00\x00\x00\x00\x00", $_->{moduledataoffset}, $_->{size});
                }
                if($hdrptroff == -1) {
                    $hdrptroff = FindNKROMHDRPointer($moduledata, $prevROMHDRAddy . "\x00\x00\x00\x00", $_->{moduledataoffset}, $_->{size});
                }
                if($hdrptroff == -1) {
                    $hdrptroff = FindNKROMHDRPointer($moduledata, $prevROMHDRAddy, $_->{moduledataoffset}, $_->{size});
                }

                if($hdrptroff >= 0) {
                    $moduledata = substr($moduledata, 0, $hdrptroff) . pack("V", $rominfo->{romheaderoffset}) . substr($moduledata, $hdrptroff + 0x04);
                }
            }
        }
    }

    return $moduledata;
}

sub MakeSignature {
    my ($rominfo, $modules)=@_;

    # EMAC: jump instruction for UTV
    my $jumpaddress = 0x00;
    for (@$modules) {
        if($_->{name}=~/^nk.exe$/i) {
            $jumpaddress = $_->{ulEntryPointOffset};
            last;
        }
    }

    my $signature = "";
    if($jumpaddress > 0) {
        $signature = ("\0" x 4) . pack("v", ($jumpaddress >> 0x10))."\x1A\x3C" . pack("v", ($jumpaddress & 0xFFFF))."\x5A\x37" . "\x08\x00\x40\x03" . ("\0" x 48) . "ECEC" . pack("V", $rominfo->{romheaderoffset}) . ("\0" x (4096-64-8));
    } else { 
        $signature = ("\0" x 64) . "ECEC" . pack("V", $rominfo->{romheaderoffset}) . ("\0" x (4096-64-8));
    }

    return $signature;
}
sub MakeRomInfo {
    my ($rominfo)= @_;
    $rominfo->{dllfirst} ||= 0x01ae0000; # EMAC: change default for UTV; was 0 : don't reserve memory
    $rominfo->{dlllast}  ||= 0x02000000; # EMAC: change default for UTV; was 0
    
    $rominfo->{physfirst}=$rominfo->{loadingoffset};

    $rominfo->{romheaderoffset}= $rominfo->{loadingoffset}+0x1000+$rominfo->{moduledatasize}+$rominfo->{filedatasize}+$rominfo->{copydatasize}+$rominfo->{modulenamessize}+$rominfo->{filenamessize}+$rominfo->{copylistsize};

    $rominfo->{physlast}=$rominfo->{romheaderoffset}+$rominfo->{nummods}*8*4 + $rominfo->{numfiles}*7*4 + 21*4;

    $rominfo->{ulRAMStart} ||= $rominfo->{potentialRAMStart} || 0x81063000;
    $rominfo->{ulRAMFree}  ||= $rominfo->{potentialRAMFree}  || 0x8106E000;
    $rominfo->{ulRAMEnd}   ||= 0x82000000;

    if($rominfo->{numcopy} > 0) {
        $rominfo->{ulCopyEntries}=$rominfo->{numcopy};
        $rominfo->{ulCopyOffset}=$rominfo->{loadingoffset}+0x1000+$rominfo->{moduledatasize}+$rominfo->{filedatasize}+$rominfo->{copydatasize}+$rominfo->{modulenamessize}+$rominfo->{filenamessize};
    } else {
        $rominfo->{ulCopyEntries}=0;
        $rominfo->{ulCopyOffset}=0;
    }
    
    $rominfo->{ulProfileLen}=0;
    $rominfo->{ulProfileOffset}=0;
    
    $rominfo->{ulKernelFlags} ||= 0;   # often this is 2, - not-all-kmode : KFLAG_NOTALLKMODE
    
    $rominfo->{ulFSRamPercent} ||= 0x00000020; # EMAC: changed default for UTV; was 0x80808080;
    
    $rominfo->{ulDrivglobStart}=0;
    $rominfo->{ulDrivglobLen}=0;
    
    $rominfo->{usCPUType} ||= 0x166;  # EMAC: Added the ability to change in userspec; default=>mips=0x166

    $rominfo->{usMiscFlags} ||=0; # EMAC: Added the ability to change in userspec
    
    # pointer to location after header+toc entries
    $rominfo->{pExtensions} =0;
    
    $rominfo->{ulTrackingStart} =0;
    
    $rominfo->{ulTrackingLen}=0;
}
sub MakeRomHeader {
    my ($rominfo, $modlist, $filelist)= @_;
    my $hdr= pack("V17v2V3", 
        $rominfo->{dllfirst},        # [0x00]
        $rominfo->{dlllast},         # [0x04]
        $rominfo->{physfirst},       # [0x08]
        $rominfo->{physlast},        # [0x0c]
        $rominfo->{nummods},         # [0x10]
        $rominfo->{ulRAMStart},      # [0x14]
        $rominfo->{ulRAMFree},       # [0x18]
        $rominfo->{ulRAMEnd},        # [0x1c]
        $rominfo->{ulCopyEntries},   # [0x20]
        $rominfo->{ulCopyOffset},    # [0x24]
        $rominfo->{ulProfileLen},    # [0x28]
        $rominfo->{ulProfileOffset}, # [0x2c]
        $rominfo->{numfiles},        # [0x30]
        $rominfo->{ulKernelFlags},   # [0x34]
        $rominfo->{ulFSRamPercent},  # [0x38]
        $rominfo->{ulDrivglobStart}, # [0x3c]
        $rominfo->{ulDrivglobLen},   # [0x40]
        $rominfo->{usCPUType},       # [0x44]
        $rominfo->{usMiscFlags},     # [0x46]
        $rominfo->{pExtensions},     # [0x48]
        $rominfo->{ulTrackingStart}, # [0x4c]
        $rominfo->{ulTrackingLen},   # [0x50]
        # [0x54]
    );

    my @modentries;
    for my $modidx (0..$rominfo->{nummods}-1) {
        my $modinfo= $modlist->[$modidx];
        push @modentries, pack("LLLLLLLL", 
            $modinfo->{dwFileAttributes}, # [0x00]
            $modinfo->{ftTime}{low},      # [0x04]
            $modinfo->{ftTime}{high},     # [0x08]
            $modinfo->{nFileSize},        # [0x0c]
            $modinfo->{lpszFileName},     # [0x10]
            $modinfo->{ulE32Offset},      # [0x14]
            $modinfo->{ulO32Offset},      # [0x18]
            $modinfo->{ulLoadOffset},     # [0x1c]
            # [0x20]
        );
    }
    my @filentries;
    for my $filidx (0..$rominfo->{numfiles}-1) {
        my $fileinfo= $filelist->[$filidx];
        push @filentries, pack("LLLLLLL", 
            $fileinfo->{dwFileAttributes}, # [0x00]
            $fileinfo->{ftTime}{low},      # [0x04]
            $fileinfo->{ftTime}{high},     # [0x08]
            $fileinfo->{nRealFileSize},    # [0x0c]
            $fileinfo->{nCompFileSize},    # [0x10]
            $fileinfo->{lpszFileName},     # [0x14]
            $fileinfo->{ulLoadOffset},     # [0x18]
            # [0x1c]
        );
    }

    return join "", $hdr, @modentries, @filentries;
}

sub GetFileList {
    # EMAC: added get_modules to scan for exes and dlls
    my ($filedir, $get_modules, $get_copylist)= @_;

    return [] unless ($filedir);

    opendir(DIR, $filedir) or warn "$!: reading $filedir\n";
    my @files= readdir DIR;
    closedir DIR;

    my @fileinfo;
    for (sort { filepos($a)<=>filepos($b) || lc($a) cmp lc($b) } @files) {
        my $path= "$filedir/$_";
        # EMAC: changed. note above
        next unless -f $path && ((!$get_modules && !$get_copylist && !/\.(exe|dll)/i && !/^data_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+_?.*?\.bin$/i) || ($get_copylist && /^data_0x[0-9a-fA-F]+_0x[0-9a-fA-F]+_?.*?\.bin$/i) || ($get_modules && /\.(exe|dll)$/i));
        # EMAC: don't include IDA files.
        next unless (!/\.(id0|id1|id2|nam|til|idb)$/i);

        my $stat= stat($path);
        push @fileinfo, {
            name=>$_,
            path=>$path,
            size=>$stat->size,
            storedsize=>$stat->size,
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
sub try_load {
    my $module = shift;
    
    eval("use $module");

    return !($@);
}
sub ReadSection {
    my ($path, $offset, $size) = @_;

    my $fh= IO::File->new($path, "r") or die "$path: $!\n";
    binmode $fh;
    my $data;
    $fh->seek($offset, SEEK_SET);
    $fh->read($data, $size);

    return $data;
}
# EMAC: implented this sub for the UTV
sub PackModules {
    my ($startoffset, $userspec, $modules, $romobjs)= @_;

    my $pemodule = "Win32::PEFile";
    if (!try_load("Win32::PEFile")) {
        die("Couldn't load " . $pemodule . ". You may need to run 'cpan install " . $pemodule . "' or 'ppm install " . $pemodule . "'. Either way, this module needs to be installed!");
    }

    my $moduledata="";
    my $idx = 0;
    my $basemoduleoffset = 0;
    my $loadingpadding = 0;

    my $dllfirst = (defined($userspec->{dllfirst}) && $userspec->{dllfirst}) ? $userspec->{dllfirst} : 0x01ae0000;
    my $dlllast = (defined($userspec->{dlllast}) && $userspec->{dlllast}) ? $userspec->{dlllast} : 0x02000000;

    for $idx (0..(scalar(@$modules)-1)) {
        my $pe = Win32::PEFile->new(-file => $modules->[$idx]->{path});

        $modules->[$idx]->{created} = $pe->{"COFFHeader"}->{"TimeDateStamp"};

        my $sname;
        my @pesections = sort { $pe->{"SecData"}->{$a}->{"header"}->{"PointerToRawData"} <=> $pe->{"SecData"}->{$b}->{"header"}->{"PointerToRawData"} } keys(%{$pe->{"SecData"}});
        if($#pesections > 0) {
            my %romsecdata = (
                "EXP_rva" => 0, # Export table, .edata
                "EXP_size" => 0,
                "IMP_rva" => 0, # Import table, .idata
                "IMP_size" => 0,
                "RES_rva" => 0, # Resource table, .rsrc
                "RES_size" => 0,
                "EXC_rva" => 0, # Exception table, .pdata
                "EXC_size" => 0,
                "SEC_rva" => 0, # Security table
                "SEC_size" => 0,
                "FIX_rva" => 0, # Fixup table
                "FIX_size" => 0,
                "DEB_rva" => 0, # Debug table, .text
                "DEB_size" => 0,
                "IMD_rva" => 0, # Image description table
                "IMD_size" => 0,
                "MSP_rva" => 0, # Machine-specific table
                "MSP_size" => 0
            );

            $modules->[$idx]->{moduledataoffset} = length($moduledata);


            if($basemoduleoffset == 0)
            {
                if($pe->{"OptionalHeader"}->{"ImageBase"} >= $startoffset)
                {
                    $basemoduleoffset = $pe->{"OptionalHeader"}->{"ImageBase"};
                }
                else
                {
                    $basemoduleoffset = $startoffset+0x1000;
                }

                $modules->[$idx]->{loadingoffset} = $basemoduleoffset;
            }
            else
            {
                $modules->[$idx]->{loadingoffset} = $basemoduleoffset + $modules->[$idx]->{moduledataoffset} + $loadingpadding;
            }

            $loadingpadding += 0x2000;


            if(defined($pe->{"SecData"}->{".text"})) {
                # EMAC: "Good Enough" but I'm assuming .text will always be first
                $modules->[$idx]->{entrypointoffset} = $startoffset+0x1000 + $modules->[$idx]->{moduledataoffset} + ($pe->{"OptionalHeader"}->{"AddressOfEntryPoint"}-$pe->{"OptionalHeader"}->{"BaseOfCode"});
            } else {
                $modules->[$idx]->{entrypointoffset} = $startoffset+0x1000 + $modules->[$idx]->{moduledataoffset};
            }

            my $sectioncnt = 0;
            for $sname (@pesections) {
                my $romseckey = "";

                my $rva = $pe->{"SecData"}->{$sname}->{"header"}->{"VirtualAddress"};

                if($sname eq ".text") {
                    $romseckey = "DEB";
                } elsif($sname eq ".pdata") {
                    $romseckey = "EXC";
                } elsif($sname eq ".rsrc") {
                    $romseckey = "RES";
                } elsif($sname eq ".reloc") {
                    $romseckey = "FIX";
                }

                if($romseckey ne "") {
                    $romsecdata{$romseckey . "_rva"} = $rva;
                    if($romseckey eq "DEB")
                    {
                        $romsecdata{$romseckey . "_size"} = 0x1c; # For some reason the UTV builds alway has this as 0x1c. No idea why and am just setting this to be consistent.
                    }
                    else
                    {
                        $romsecdata{$romseckey . "_size"} = $pe->{"SecData"}->{$sname}->{"header"}->{"VirtualSize"};
                    }
                }

                if($pe->{"SecData"}->{$sname}->{"header"}->{"PointerToRawData"} == 0 || $pe->{"SecData"}->{$sname}->{"header"}->{"SizeOfRawData"} == 0) {
                    next;
                }

                $sectioncnt++;

                my $addrbase = $pe->{"OptionalHeader"}->{"ImageBase"};
                if($addrbase >= $startoffset) {
                    $addrbase -= ($startoffset - 0x10000);
                }

                my $readaddr = ($addrbase + $rva);
                if ($modules->[$idx]->{path}=~/\.dll$/i) {
                    $readaddr += $dlllast;
                }

                push(@$romobjs, {
                    "moduleidx" => $idx,
                    "filename" => $modules->[$idx]->{name},
                    "path" => $modules->[$idx]->{path},
                    "name" => $sname,
                    "flags" => $pe->{"SecData"}->{$sname}->{"header"}->{"Characteristics"},
                    "rva" => $rva,
                    "dataptr" => $startoffset + 0x1000 + length($moduledata),
                    "realaddr" => $readaddr,
                    "psize" => $pe->{"SecData"}->{$sname}->{"header"}->{"SizeOfRawData"},
                    "vsize" => $pe->{"SecData"}->{$sname}->{"header"}->{"VirtualSize"}
                });

                my $pesecdata = ReadSection($modules->[$idx]->{path}, $pe->{"SecData"}->{$sname}->{"header"}->{"PointerToRawData"}, $pe->{"SecData"}->{$sname}->{"header"}->{"SizeOfRawData"});
                $moduledata .= $pesecdata;

                # EMAC: note- this doesn't match the UTV exactly. Need to figure out why sections are ordered the way they are.
                if ($romobjs->[$idx]{path}=~/\.dll$/i && (length($moduledata)&0xff)) {
                    $moduledata .= "\0" x (0x100-(length($moduledata)&0xff));
                }
            }

            if ($romobjs->[$idx]{path}=~/\.dll$/i && (length($moduledata)&0xfff)) {
                $moduledata .= "\0" x (0x1000-(length($moduledata)&0xfff));
            }

            if(defined($pe->{"DataDir"}->{".edata"}) && $pe->{"DataDir"}->{".edata"}->{"size"} > 0) {
                $romsecdata{"EXP_rva"} = $pe->{"DataDir"}->{".edata"}->{"imageRVA"};
                $romsecdata{"EXP_size"} = $pe->{"DataDir"}->{".edata"}->{"size"};
            }

            if(defined($pe->{"DataDir"}->{".idata"}) && $pe->{"DataDir"}->{".idata"}->{"size"} > 0) {
                $romsecdata{"IMP_rva"} = $pe->{"DataDir"}->{".idata"}->{"imageRVA"};
                $romsecdata{"IMP_size"} = $pe->{"DataDir"}->{".idata"}->{"size"};
            }

            if ((length($moduledata)&0x3)) {
                $moduledata .= "\0" x (0x4-(length($moduledata)&0x3));
            }
            
            my $imageflags = $pe->{"COFFHeader"}->{"Characteristics"};
            # The UTV has the metadata for a reolocations table but the actual section is never included.
            # So this should always end up in the else statement. The metadata is stripped when the image is dumped.
            #if($romsecdata{"FIX_rva"} > 0 && $romsecdata{"FIX_size"} > 0 && defined($pe->{"SecData"}->{".reloc"}) && $pe->{"SecData"}->{".reloc"}->{"header"}->{"SizeOfRawData"} > 0)
            #{
            #    $imageflags &= 0xfffe; # Removing IMAGE_FILE_RELOCS_STRIPPED
            #}
            #else
            #{
            #    $imageflags |= 0x01; # Add IMAGE_FILE_RELOCS_STRIPPED
            #}

            $modules->[$idx]->{e32offset} = $startoffset + 0x1000 + length($moduledata);
            $moduledata .= pack(
                "v2V2v2V2v2V18",
                $sectioncnt,                                        # objcnt      [0x00]
                $imageflags,                                        # imageflags  [0x02]
                $pe->{"OptionalHeader"}->{"AddressOfEntryPoint"},   # entryrva    [0x04]
                $pe->{"OptionalHeader"}->{"ImageBase"},             # vbase       [0x08]
                $pe->{"OptionalHeader"}->{"MajorSubsystemVersion"}, # subsysmajor [0x0c]
                $pe->{"OptionalHeader"}->{"MinorSubsystemVersion"}, # subsysminor [0x0e]
                $pe->{"OptionalHeader"}->{"SizeOfStackReserve"},    # stackmax    [0x10]
                $pe->{"OptionalHeader"}->{"SizeOfImage"},           # vsize       [0x14]
                $pe->{"OptionalHeader"}->{"Subsystem"},             # subsys      [0x18]
                $pe->{"OptionalHeader"}->{"DllCharacteristics"},    # dllflags    [0x1a]
                # [-0x48]
                $romsecdata{"EXP_rva"},                             # 0 EXP_rva   [0x1c]
                $romsecdata{"EXP_size"},                            # 0 EXP_size  [0x20]
                $romsecdata{"IMP_rva"},                             # 1 IMP_rva   [0x24]
                $romsecdata{"IMP_size"},                            # 1 IMP_size  [0x28]
                $romsecdata{"RES_rva"},                             # 2 RES_rva   [0x2c]
                $romsecdata{"RES_size"},                            # 2 RES_size  [0x30]
                $romsecdata{"EXC_rva"},                             # 3 EXC_rva   [0x34]
                $romsecdata{"EXC_size"},                            # 3 EXC_size  [0x38]
                $romsecdata{"SEC_rva"},                             # 4 SEC_rva   [0x3c]
                $romsecdata{"SEC_size"},                            # 4 SEC_size  [0x40]
                $romsecdata{"FIX_rva"},                             # 5 FIX_rva   [0x44]
                $romsecdata{"FIX_size"},                            # 5 FIX_size  [0x48]
                $romsecdata{"DEB_rva"},                             # 6 DEB_rva   [0x4c]
                $romsecdata{"DEB_size"},                            # 6 DEB_size  [0x50]
                $romsecdata{"IMD_rva"},                             # 7 IMD_rva   [0x54]
                $romsecdata{"IMD_size"},                            # 7 IMD_size  [0x58]
                $romsecdata{"MSP_rva"},                             # 8 MSP_rva   [0x5c]
                $romsecdata{"MSP_size"}                             # 8 MSP_size  [0x60]
                # [0x64]
            );
        }
    }

    my $currentname = "";
    for $idx ((0..(scalar(@$romobjs) - 1))) {
        if($currentname ne $romobjs->[$idx]{path}) {
            if ((length($moduledata)&0x3)) {
                $moduledata .= "\0" x (0x4-(length($moduledata)&0x3));
            }

            $currentname = $romobjs->[$idx]{path};
            $modules->[$romobjs->[$idx]{moduleidx}]->{o32offset} = $startoffset + 0x1000 + length($moduledata);
        }

        $moduledata .= pack("V6",
            $romobjs->[$idx]{vsize},
            $romobjs->[$idx]{rva},
            $romobjs->[$idx]{psize},
            $romobjs->[$idx]{dataptr},
            $romobjs->[$idx]{realaddr},
            $romobjs->[$idx]{flags}
        );
    }

    if ((length($moduledata)&0xff)) {
        $moduledata .= "\0" x (0x100-(length($moduledata)&0xff));
    }

    return $moduledata;
}

sub may_compress_file {
    my ($path)= @_;

    $path =~ s/.*\///;

    return !exists $g_nocompress{lc($path)};
}
sub is_compressed_file {
    my ($path, $data)= @_;

    $path =~ s/.*\///;

    if(exists $g_precompressed{lc($path)}) {
        return $data, $g_precompressed{lc($path)};
    } else {
        return undef;
    }
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


        # EMAC: Don't compress any any files. This is done before we get here.
        #my $compressed= $compress->($data) if (may_compress_file($_->{path}));
        my ($compressed, $uncompressed_size) = is_compressed_file($_->{path}, $data); # EMAC: added

        if (defined $compressed && length($compressed)<$uncompressed_size) {
            $filedata .= $compressed;
            $_->{size} = $uncompressed_size; # EMAC: Added
            $_->{storedsize} = length($compressed);
        }
        else {
            $filedata .= $data;
            $_->{storedsize}= length($data);
        }
    }

    if ((length($filedata)&0xff)) {
        $filedata .= "\0" x (0x100-(length($filedata)&0xff));
    }

    return $filedata;
}
sub PackCopyEntries {
    my ($startoffset, $userspec, $copyentries, $romobjs)= @_;

    my $copylistdata = "";

    for (@$copyentries) {
        $_->{copydataoffset}= length($copylistdata);

        my ($from, $to, $exesection) = ($_->{path}=~/data_0x([0-9a-fA-F]+)_0x([0-9a-fA-F]+)(_?.*?)\.bin$/i);

        $_->{dest} = hex($from);
        $_->{destlen} = (hex($to) - hex($from));

        if($exesection) {
            my ($exefilename, $exesection) = ($exesection=~/^_(.*?)\-(\.[a-zA-Z0-9]+)$/i);

            my $sec;
            for $sec (@$romobjs) {
                if($sec->{filename} eq $exefilename && $sec->{name} eq $exesection) {
                    $_->{copydataoffset} = -1;
                    $_->{size} = $sec->{psize};
                    $_->{loadingoffset} = $sec->{dataptr};
                }
            }
        } else {

            my $fh= IO::File->new($_->{path}, "r") or die "$_->{path}: $!\n";
            binmode $fh;
            my $data;
            $fh->read($data, $_->{size});

            $copylistdata .= $data;
        }
    }


    if ((length($copylistdata)&0xff)) {
        $copylistdata .= "\0" x (0x100-(length($copylistdata)&0xff));
    }

    return $copylistdata;
}

sub PackNames {
    my ($files)= @_;
    
    my $namedata="";
    for (@$files) {
        $_->{nameoffset}= length($namedata);
        $namedata .= $_->{name};
        $namedata .= "\0";
        my $namelen= length($_->{name})+1;
    }

    if ((length($namedata)&0xf)) {
        $namedata .= "\0" x (0x10-(length($namedata)&0xf));
    }

    return $namedata;
}

# EMAC: UTV copies the .data section of nk.exe. Keeping it like this (for now?) so it's easier (afaik) to unpack and then pack again (the dest address isn't encoded easily in the exe).
sub PackCopyList {
    my ($loadingoffset, $moduledatasize, $filedatasize, $copyentries)= @_;

    my $potentialRAMStart = 0;
    my $potentialRAMFree = 0;

    my $copylistdata = "";
    for (@$copyentries) {
        $potentialRAMStart = $_->{dest};
        $potentialRAMFree = ($_->{dest} + $_->{destlen});
        if($potentialRAMFree&0xfff) {
            $potentialRAMFree += (0x1000-($potentialRAMFree&0xfff))
        }

        if($_->{copydataoffset} >= 0) {
            $copylistdata .= pack("LLLL", 
                $loadingoffset+0x1000+$moduledatasize+$filedatasize+$_->{copydataoffset},
                $_->{dest},
                $_->{size},
                $_->{destlen},
            );
        } elsif(defined($_->{loadingoffset}) && $_->{loadingoffset}) {
            $copylistdata .= pack("LLLL", 
                $_->{loadingoffset},
                $_->{dest},
                $_->{size},
                $_->{destlen},
            );
        }
    }
    
    if ((length($copylistdata)&0x1ff)) {
        $copylistdata .= "\0" x (0x200-(length($copylistdata)&0x1ff));
    }

    return $copylistdata, $potentialRAMStart, $potentialRAMFree;
} 

sub MakeModuleEntries {
    my ($rominfo, $modules)=@_;
    for (@$modules) {
        $_->{dwFileAttributes}= 1 | ($_->{size}>$_->{storedsize} ? 0x2000 : 0);  # readonly + optional compressed
        $_->{ftTime}=   MakeFILETIME($_->{created});
        $_->{nFileSize}=    $_->{size};
        $_->{lpszFileName}=  $rominfo->{loadingoffset}+0x1000+$rominfo->{moduledatasize}+$rominfo->{filedatasize}+$rominfo->{copydatasize}+$_->{nameoffset};
        $_->{ulE32Offset}=    $_->{e32offset}; # todo; EMAC: changed for UTV
        $_->{ulO32Offset}=    $_->{o32offset}; # todo; EMAC: changed for UTV
        $_->{ulLoadOffset}=   $_->{loadingoffset}; # todo; EMAC: changed for UTV
        $_->{ulEntryPointOffset} = $_->{entrypointoffset};
    }
}
sub MakeFileEntries {
    my ($rominfo, $files)=@_;
    for (@$files) {
        $_->{dwFileAttributes}= 1 | ($_->{size}>$_->{storedsize} ? 0x800 : 0);  # readonly + optional compressed
        $_->{ftTime}=   MakeFILETIME($_->{created});
        $_->{nRealFileSize}=    $_->{size};
        $_->{nCompFileSize}=    $_->{storedsize};
        $_->{lpszFileName}=  $rominfo->{loadingoffset}+0x1000+$rominfo->{moduledatasize}+$rominfo->{filedatasize}+$rominfo->{copydatasize}+$rominfo->{modulenamessize}+$_->{nameoffset};
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
