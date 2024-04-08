#!perl -w
# (C) 2003-2007 Willem Jan Hengeveld <itsme@xs4all.nl>
# Web: http://www.xs4all.nl/~itsme/
#      http://wiki.xda-developers.com/
#
# $Id$
#
#  G:\archive\software\WINCE420/PUBLIC/COMMON/OAK/INC/pehdr.h
#  G:\archive\software\WINCE420/PUBLIC/COMMON/OAK/INC/romldr.h
#
#
# .... i think the problem is that there are 2 xip section both at the same virtual address
#  ... see for instance decompress data of ceconfig.h
#    ... it returns the wrong data.

use strict;
$|=1;
use Getopt::Long;
use IO::File;
use Carp;

my $g_fileseek;
my $g_doprint= 0;
my $g_addblankreloctable = 1; # EMAC: testing for the UTV. Imagesize includes a blank .reloc table
my $g_savedir;
my $g_use_wince3_compression=1; # EMAC: this is used as a flag for the rva in PE files. Always turn this on for UTV.
my %seen_extensions;
my %g_xipchaininfo;
my $g_verbose;
my $g_list;

#use XdaDevelopers::CompressUtils;
# this requires a patch to Win32::API, which can be found at
#   http://www.xs4all.nl/~itsme/projects/perl/Win32-API-0.41-wj2.tar.gz
#use Win32::API;
# CEDecompress is to be used for wince3.x roms
# CEDecompressROM is to be used for wince4.x roms
#
# problem is that this call sometimes crashes the app.
# 
#
#my $g_decompress= Win32::API->new("CECompress.dll", "CEDecompress", "PNPNNNN", "N", "_cdecl")
#my $g_decompress= Win32::API->new("CECompress.dll", "CEDecompressROM", "PNPNNNN", "N", "_cdecl")
#     or warn "error importing CEDecompress: $!\n";

GetOptions(
    "s=s"=> sub { $g_fileseek= eval($_[1]); },
    "d:s"=> \$g_savedir,
    "3"  => \$g_use_wince3_compression,
    "v"=> \$g_verbose,
    "l"=> \$g_list,
) or die usage();

sub usage {
    return <<__EOF__
Usage: dumpxip.pl -o baseoffet [-l length] [-d savedir] [-s fileseek] romfile
__EOF__
}

my $g_filename= shift or die usage();

die "$g_filename not found\n" if (!-e $g_filename);


my $g_data= ReadFile($g_filename, $g_fileseek);

my $rom= ROM->new($g_data);
my $mem= MemSpace->new();
my $xipblocks= XipBlock::FindXipBlocks($rom);

# [0x00000000, 0x10078000], [0x00100000, 0x80000000], [0x00900000, 0x82040000], [0x015c0000, 0x82d00000], [0x01640000, 0x82d80000], [0x01940000, 0x83080000] 
for my $xipblock ( @$xipblocks ) {
    printf("romdump, 0x%08lx 0x%08lx\n", $xipblock->{ofs}, $xipblock->{base});
    $rom->setbase($xipblock->{ofs}, $xipblock->{base});
    $mem->setvbase($xipblock->{ofs}, $xipblock->{base});
    my $xip= XipBlock->new($rom, $mem, $xipblock->{base});

    $xip->ParseXipBlock();
    $xip->DumpInfo();

    $xip->PrintFileList();

    $xipblock->{parsedxip}= $xip;
}
$mem->pfillblanks($rom, 0, $rom->{size});
$mem->print();
if (defined $g_savedir && length($g_savedir)>0) {
    my $xipindex= 1;
    for my $xipblock ( @$xipblocks ) {
        $rom->setbase($xipblock->{ofs}, $xipblock->{base});
        $mem->setvbase($xipblock->{ofs}, $xipblock->{base});
        my $xipname= exists $g_xipchaininfo{$xipblock->{base}} ? "xip_".$g_xipchaininfo{$xipblock->{base}}{szName} : sprintf("xip_%02d", $xipindex);

        if(!$g_list) {
            $xipblock->{parsedxip}->SaveFiles($g_savedir, $xipname);
        }

        $xipindex++;
    }
}
print "finished\n";
exit(0);

sub ReadFile {
    my $fn= shift;
    my $ofs= shift || 0;
    my $len= shift || (-s $fn)-$ofs;
    my $data;
    my $fh= IO::File->new($fn, "r") or die "$fn: $!";
    binmode $fh;
    $fh->seek($ofs, SEEK_SET);
    $fh->read($data, $len);
    $fh->close();

    return $data;
}

#############################################################################
#############################################################################
package XipBlock;
use POSIX;
use strict;
use Carp;
use Dumpvalue;

sub new {
    my $class= shift;
    my $rom= shift;
    my $mem= shift;
    my $start= shift;

    return bless { rom_type=>undef, xipstart=>$start, rom=>$rom, mem=>$mem }, $class;
}
sub ParseXipBlock {
    my $self= shift;

    my $rom= $self->{rom};
    my $mem= $self->{mem};

    if ($rom->GetDword($self->{xipstart}+0x40) != 0x43454345) {
        die "ECEC signature not found\n";
    }

    my $romhdrofs= $rom->GetDword($self->{xipstart}+0x44);
    $mem->vadd($self->{xipstart}+0x40, 8, "ECEC signature + romhdr ptr");
    my $romhdr= $self->{romhdr}= $self->ParseRomHdr($rom->GetVData($romhdrofs, 0x54));

    printf("xipblock 0x%08x-?, hdr=0x%08x\n", $self->{xipstart}, $self->{romhdr}) if ($g_verbose);

    $self->{o32sections}= {}; # EMAC: added for UTV copy entry info

    $mem->vadd($romhdrofs, 0x54, $romhdr->{desc});
    my $modlistofs= $romhdrofs+ 0x54;
    my $modules= $self->{modules}= $self->ParseModulesList($rom->GetVData($modlistofs, 0x20*$romhdr->{nummods}));
    $mem->vadd($modlistofs, 0x20*$romhdr->{nummods}, "modules list, %d modules", $romhdr->{nummods});
    $_->{filename}= $rom->GetString($_->{lpszFileName}) for (@$modules);

    my $filesofs= $modlistofs + 0x20*$romhdr->{nummods};
    my $files= $self->{files}= $self->ParseFilesList($rom->GetVData($filesofs, 0x1c*$romhdr->{numfiles}));
    $mem->vadd($filesofs, 0x1c*$romhdr->{numfiles}, "files list, %d files", $romhdr->{numfiles});
    $_->{filename}= $rom->GetString($_->{lpszFileName}) for (@$files);

    if ($romhdr->{ulCopyEntries}) {
        $self->{copylist}= $self->ParseCopyList($rom->GetVData($romhdr->{ulCopyOffset}, 0x10*$romhdr->{ulCopyEntries}));
        $mem->vadd($romhdr->{ulCopyOffset}, 0x10*$romhdr->{ulCopyEntries}, "copy list, %d entries", $romhdr->{ulCopyEntries});
    }
    else {
        $self->{copylist}= [];
    }

    $self->AddModuleHeaders($_) for (@{$modules});

    $self->ParseExtensions($romhdr->{pExtensions});
}
sub ParseExtension {
    my $self= shift;
    my $data= shift;
    my @fields= unpack("A24V5", $data);
    my @names= qw(name type pdata length reserved pNextExt);
    my @fmt= qw(%s 0x%08lx 0x%08lx 0x%08lx 0x%08lx 0x%08lx);
    return  {
        desc=>sprintf("extension: %s", join ", ", map { sprintf("%s:$fmt[$_]", $names[$_], $fields[$_]) } (0..$#names)),
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}
sub isValidRomOfs {
    my ($ofs)= @_;
    return ($ofs>=0x80000000 && $ofs<0xa0000000);
}
sub ParseExtensions {
    my ($self, $extptr)= @_;

    my $first=1;
    while ($extptr) {
        last if (!$self->{rom}->IsInRange($extptr));

        last if ($seen_extensions{$extptr});

        $seen_extensions{$extptr}= 1;

        my $ext= $self->ParseExtension($self->{rom}->GetVData($extptr, 44));

        last if (
            ($ext->{pdata}!=0 && !isValidRomOfs($ext->{pdata}))
            ||($ext->{pNextExt}!=0 && !isValidRomOfs($ext->{pNextExt}))
            ||$ext->{length}>0x1000000);

        if (!$first) {
            $self->{mem}->vadd($extptr, 44, $ext->{desc});
            $self->{mem}->vadd($ext->{pdata}, $ext->{length}, "data for extension %s: %s", $ext->{name},
                join(",", map { sprintf("0x%08lx", $_); } unpack("V*", $self->{rom}->GetVData($ext->{pdata}, $ext->{length})))
            ) if ($ext->{pdata});
        }

        $first= 0;

        $extptr= $ext->{pNextExt};
    }
}
sub SaveFiles {
    my $self= shift;
    my $savedir= shift;
    my $xipname= shift;

    if (defined($savedir) && length($savedir)>0) {
        mkdir $savedir;
    }
    $savedir .= "/";#$xipname";
    if ($savedir) {
        mkdir $savedir;
    }

    die "$savedir does not exist\n" if (!-d $savedir);

    print "saving files to $savedir\n";
    $self->SaveFile($_, $savedir) for (@{$self->{files}});
    print "saving modules to $savedir\n";
    $self->SaveModule($_, $savedir) for (@{$self->{modules}});
    print "saving copy entries to $savedir\n"; # EMAC: added for the UTV
    $self->SaveCopyEntry($_, $savedir) for (@{$self->{copylist}});
}
sub DumpInfo {
    my $self= shift;
    $self->DumpFilesAreas();
    $self->DumpModulesAreas();
    $self->DumpCopyEntryAreas();

    $self->{mem}->vfillblanks($self->{rom}, $self->{romhdr}{physfirst}, $self->{romhdr}{physlast});
    #$self->{mem}->print();
}
sub filetimestring {
    my ($file)= @_;

    # 100 ns intervals since 1-1-1601
    my $win32ftime= $file->{ftTime_high}*(2**32)+$file->{ftTime_low};

    my $unixtime= int($win32ftime/10000000.0-11644473600);
    #return sprintf("0x%08lx0x%08lx", $file->{ftTime_high}, $file->{ftTime_low});
    return POSIX::strftime("%Y-%m-%d %H:%M:%S", localtime $unixtime);
}
sub PrintFile {
    my ($self, $file)= @_;
    printf("0x%08lx %6d %s %s\n", 
        $file->{ulLoadOffset}, 
        exists $file->{nRealFileSize}?$file->{nRealFileSize}:$file->{nFileSize}, 
        filetimestring($file), 
        $file->{filename});
}
sub PrintCopyEntry {
    my ($self, $copyentry)= @_;

    printf("0x%08lx %6d ------------------- 0x%08lx to 0x%08lx\n", 
        $copyentry->{ulSource}, 
        $copyentry->{ulCopyLen}, 
        $copyentry->{ulDest}, 
        $copyentry->{ulDest} + $copyentry->{ulDestLen}
    );
    
}
sub PrintFileList {
    my ($self)= @_;
    printf("--files\n");
    $self->PrintFile($_) for (@{$self->{files}});
    printf("--modules\n");
    $self->PrintFile($_) for (@{$self->{modules}});
    printf("--copy entries\n");
    $self->PrintCopyEntry($_) for (@{$self->{copylist}});
}

sub ParseRomHdr {
    my $self= shift;
    my $data= shift;
    my @fields= unpack("V17v2V3", $data);
    my @names= qw(dllfirst dlllast physfirst physlast nummods ulRAMStart ulRAMFree ulRAMEnd ulCopyEntries ulCopyOffset ulProfileLen ulProfileOffset numfiles ulKernelFlags ulFSRamPercent ulDrivglobStart ulDrivglobLen usCPUType usMiscFlags pExtensions ulTrackingStart ulTrackingLen);
    return  {
        desc=>sprintf("romhdr : %s", join ", ", map { sprintf("%s:0x%08lx", $names[$_], $fields[$_]) } (0..$#names)),
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}
sub ParseModulesList {
    my $self= shift;
    my $data= shift;
    my @modules;

    my $i;
    for ($i= 0 ; $i<length($data) ; $i+=0x20) {
        push @modules, ParseModuleEntry(substr($data, $i, 0x20), sprintf("module entry %d", $i/0x20));
    }
    if ($i!=length($data)) {
        warn "uneven modules list\n";
    }

    return \@modules;
}
sub ParseModuleEntry {
    my $data= shift;
    my $desc= shift;
    my @fields= unpack("V8", $data);
    my @names= qw(dwFileAttributes ftTime_low ftTime_high nFileSize lpszFileName ulE32Offset ulO32Offset ulLoadOffset);
    return  {
        desc=>sprintf("%s : %s", $desc, join ", ", map { sprintf("%s:0x%08lx", $names[$_], $fields[$_]) } (0..$#names)),
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}
sub ParseFilesList {
    my $self= shift;
    my $data= shift;
    my @files;

    my $i;
    for ($i= 0 ; $i<length($data) ; $i+=0x1c) {
        push @files, $self->ParseFilesEntry(substr($data, $i, 0x1c), sprintf("files entry %d", $i/0x1c));
    }
    if ($i!=length($data)) {
        warn "uneven files list\n";
    }

    return \@files;
}
sub ParseFilesEntry {
    my $self= shift;
    my $data= shift;
    my $desc= shift;
    my @fields= unpack("V7", $data);
    my @names= qw(dwFileAttributes ftTime_low ftTime_high nRealFileSize nCompFileSize lpszFileName ulLoadOffset);
    return  {
        desc=>sprintf("%s : %s", $desc, join ", ", map { sprintf("%s:0x%08lx", $names[$_], $fields[$_]) } (0..$#names)),
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}
sub ParseCopyList {
    my $self= shift;
    my $data= shift;
    my @list;

    my $i;
    for ($i= 0 ; $i<length($data) ; $i+=0x10) {
        push @list, $self->ParseCopyEntry(substr($data, $i, 0x10), sprintf("copy entry %d", $i/0x10));
    }
    if ($i!=length($data)) {
        warn "uneven copy list\n";
    }

    return \@list;
}
sub ParseCopyEntry {
    my $self= shift;
    my $data= shift;
    my $desc= shift;
    my @fields= unpack("V4", $data);
    my @names= qw(ulSource ulDest ulCopyLen ulDestLen);
    return  {
        desc=>sprintf("%s : %s", $desc, join ", ", map { sprintf("%s:0x%08lx", $names[$_], $fields[$_]) } (0..$#names)),
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}
my $last_module = 0;
sub AddModuleHeaders {
    my $self= shift;
    my $module= shift;
    my $rom= $self->{rom};
    my $mem= $self->{mem};

    if (!defined $self->{rom_type}) {
        $self->{rom_type}= determine_rom_type($rom->GetVData($module->{ulE32Offset}, 0x70));
    }
    if ($self->{rom_type}==2) {
        $module->{e32}= ParseE32Header_v2($rom->GetVData($module->{ulE32Offset}, 0x64));

        $mem->vadd($module->{ulE32Offset}, 0x64, "UTV e32 header %s", $module->{filename});
    }
    elsif ($self->{rom_type}==5) {
        $module->{e32}= ParseE32Header_v5($rom->GetVData($module->{ulE32Offset}, 0x6e));
        $mem->vadd($module->{ulE32Offset}, 0x6e, "e32 header %s", $module->{filename});
    }
    elsif ($self->{rom_type}==4) {
        $module->{e32}= ParseE32Header_v4($rom->GetVData($module->{ulE32Offset}, 0x6a));
        $mem->vadd($module->{ulE32Offset}, 0x6a, "e32 header %s", $module->{filename});
    }
    else {
        die "unknown romtype $self->{rom_type}\n";
    }
    if ($g_verbose) {
        printf("module %s\n", $module->{filename});
        printf("flags=0x%08x, entry=0x%08x, vbase/size=0x%08x/0x%08x, subsys=%d/v%d.%d, stack=0x%08x ts=0x%08x\n",
            map { $module->{e32}{$_}||0 }
                qw(imageflags entryrva vbase vsize subsys subsysmajor subsysminor stackmax timestamp));
        for my $inf (qw(sect14 EXP_ IMP_ RES_ EXC_ SEC_ FIX_ DEB_ IMD_ MSP_)) {
            if ($module->{e32}{$inf.'rva'} || $module->{e32}{$inf.'size'}) {
                printf("      %s: 0x%08x 0x%08x\n", $inf, $module->{e32}{$inf.'rva'}, $module->{e32}{$inf.'size'});
            }
        }
    }

    for my $objidx (1..$module->{e32}{objcnt}) {
        push @{$module->{o32}}, ParseO32Header($rom->GetVData($module->{ulO32Offset}+($objidx-1)*0x18, 0x18));

        printf("  o%d rva=0x%08x v:0x%08x,p:0x%08x, flag=0x%08x, real=0x%08x, ptr=0x%08x\n", $objidx-1,
                map {$module->{o32}[-1]{$_}} qw(rva vsize psize flags realaddr dataptr)) if ($g_verbose);
    }
    $mem->vadd($module->{ulO32Offset}, 0x18*$module->{e32}{objcnt}, "o32 headers %s", $module->{filename});
}
sub determine_rom_type {
    return 2; # EMAC: always return 2 for UTV
    my @f= unpack("V*", shift);
    if ($f[8] < $f[5] && $f[26]>0) {
        return 4;
    }
    else {
        return 5;
    }
}
# with extra timestamp field!
sub ParseE32Header_v5 {
    my $data= shift;
    my @fields= unpack("v2V2v2V5V18v", $data);
    my @names= qw(objcnt imageflags entryrva vbase subsysmajor subsysminor stackmax vsize sect14rva sect14size timestamp EXP_rva EXP_size IMP_rva IMP_size RES_rva RES_size EXC_rva EXC_size SEC_rva SEC_size FIX_rva FIX_size DEB_rva DEB_size IMD_rva IMD_size MSP_rva MSP_size subsys);
    return  {
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}
sub ParseE32Header_v4 {
    my $data= shift;
    my @fields= unpack("v2V2v2V4V18v", $data);
    my @names= qw(objcnt imageflags entryrva vbase subsysmajor subsysminor stackmax vsize sect14rva sect14size EXP_rva EXP_size IMP_rva IMP_size RES_rva RES_size EXC_rva EXC_size SEC_rva SEC_size FIX_rva FIX_size DEB_rva DEB_size IMD_rva IMD_size MSP_rva MSP_size subsys);
    return  {
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}
# Added for UTV
sub ParseE32Header_v2 {
    my $data= shift;
    my @fields= unpack("v2V2v2V2v2V18", $data);
    # dllflags is extra testing, unknown if it's actually dllflags
    my @names= qw(objcnt imageflags entryrva vbase subsysmajor subsysminor stackmax vsize subsys dllflags EXP_rva EXP_size IMP_rva IMP_size RES_rva RES_size EXC_rva EXC_size SEC_rva SEC_size FIX_rva FIX_size DEB_rva DEB_size IMD_rva IMD_size MSP_rva MSP_size);
    return  {
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}

sub ParseO32Header {
    my $data= shift;
    my @fields= unpack("V6", $data);
    my @names= qw(vsize rva psize dataptr realaddr flags);
    return  {
        map { ( $names[$_] => $fields[$_] ) } (0..$#names)
    };
}
sub DumpFilesAreas {
    my $self= shift;
    for my $file (@{$self->{files}}) {
        my $desc= $file->{filename};
        $self->{mem}->vadd($file->{ulLoadOffset}, $file->{nCompFileSize}, (($file->{dwFileAttributes}&0x800)?"compressed ":"")."file data %s", $desc);
        $self->{mem}->vadd($file->{lpszFileName}, length($file->{filename})+1, "file filename %s", $desc);
    }
}
sub DumpModulesAreas {
    my $self= shift;
    my $mem= $self->{mem};
    for my $mod (@{$self->{modules}}) {
        my $desc= $mod->{filename};
        $mem->vadd($mod->{lpszFileName}, length($mod->{filename})+1, "module filename %s", $desc);
        for my $o32ent (@{$mod->{o32}}) {
            my $l= $o32ent->{psize}; $l= $o32ent->{vsize} if ($o32ent->{vsize}<$l);
            $mem->vadd($o32ent->{dataptr}, $l, 
                "f%07lx v%07lx r%07lx %smodule data %s", $o32ent->{flags}, $o32ent->{rva}, $o32ent->{realaddr}, (($o32ent->{flags}&0x2000)? "compressed " : ""), $desc) if ($o32ent->{dataptr});
        }
    }
}
sub DumpCopyEntryAreas {
    my $self= shift;
    for my $file (@{$self->{copylist}}) {
        my $desc= $file->{ulDest};
        $self->{mem}->vadd($file->{ulSource}, $file->{ulCopyLen}, "copy data to 0x%08lx", $desc);
    }
}
sub GetUniqueFilename {
    my ($dir, $filename)= @_;

    my $fn= "$dir/$filename";
    my $i= 1;
    while (-e $fn) {
        $fn= sprintf("%s/%s-%d", $dir, $filename, $i++);
    }

    return $fn;
}
sub GetUncompressedData {
    my ($rom, $ofs, $size, $fullsize, $compressed)= @_;
    return "" if ($size==0);

    my $data= $rom->GetVData($ofs, $size);
    if ($compressed) {
        if ($g_use_wince3_compression && $size==$fullsize) {
            # BUG in wince3  ... often compress flag is set, while data is not compressed.
            return $data;
        }

        # EMAC: always return data, even if it's compressed. It will be decompressed later.
        # This is so I don't have to deal with XdaDevelopers::CompressUtils on Linux or
        # ask people to manually compile and install this module.
        return $data;

        #printf("decompress 0x%08lx:0x%08lx 0x%08lx -> 0x%08lx : %s\n", $ofs, $size, length($data), $fullsize, unpack("H*", $data));
        # .. append some extra data, so the (buggy) dll can read beyond the end of its input buffer.
require XdaDevelopers::CompressUtils;
        my $decomp= $g_use_wince3_compression
                ? XdaDevelopers::CompressUtils::rom3uncompress($data.("\x00" x 16), $fullsize)
                : XdaDevelopers::CompressUtils::rom4uncompress($data.("\x00" x 16), $fullsize);
        if (!defined $decomp) {
            #printf(".. error\n");
            return undef;
        }
        #printf(".. ok\n");
        return $decomp;
    }
    return $data;
}

sub IMAGE_SCN_COMPRESSED { 0x2000; }
sub FILE_ATTRIBUTE_COMPRESSED{ 0x0800; }
sub SaveFile {
    my $self= shift;
    my $rom= $self->{rom};
    my $file= shift;
    my $savedir= shift;

    my $data= GetUncompressedData($rom, $file->{ulLoadOffset}, $file->{nCompFileSize}, $file->{nRealFileSize}, $file->{dwFileAttributes}&FILE_ATTRIBUTE_COMPRESSED);
    if (!defined $data) {
        printf("ERROR decompressing file (%d -> %d) '%s'\n", $file->{nCompFileSize}, $file->{nRealFileSize}, $file->{filename});
        return;
    }
    my $filename= GetUniqueFilename($savedir, $file->{filename});
    my $fh= IO::File->new($filename, "w+") or die "$filename: $!\n";
    binmode $fh;
    $fh->print($data);
    $fh->close();
}
sub SaveModule {
    my ($self, $module, $savedir)= @_;
    
    my $module_time_t = ($module->{ftTime_high} << 0x20) + $module->{ftTime_low};

    $module_time_t /= 10000000;
    $module_time_t -= 11644473600;

    my $exe= ExeFile->new($self->{romhdr}{usCPUType} || 0x0166, int($module_time_t)); # EMAC: default to UTV CPU type, MIPS little endian

    for my $o32ent (@{$module->{o32}}) {
        my $size= $o32ent->{vsize}; $size= $o32ent->{psize} if ($size>$o32ent->{psize});

        $o32ent->{data}= GetUncompressedData($rom, $o32ent->{dataptr}, $size, $o32ent->{vsize}, $o32ent->{flags} & IMAGE_SCN_COMPRESSED);
        if (!defined $o32ent->{data}) {
            printf("ERROR decompressing section 0x%08lx-0x%08lx (%d -> %d) of '%s'\n", 
                $o32ent->{dataptr}, $o32ent->{dataptr}+$size, 
                $size, $o32ent->{vsize},
                $module->{filename});
            return;
        }
        $exe->addo32($o32ent);
    }
    $exe->adde32($module->{e32});

    my $filename= GetUniqueFilename($savedir, $module->{filename});

    my $peexe = $exe->SaveToFile($filename);

     # EMAC: added for UTV copy entry info
    for (@{$peexe->{o32obj}}) {
        $self->{o32sections}{$_->{odataptr}} = {
            "filename" => $module->{filename},
            "name" => $_->{name},
            "dataptr" => $_->{odataptr},
            "size" => $_->{psize}
        }
    }
}
sub SaveCopyEntry {
    my ($self, $copyentry, $savedir)= @_;

    my $namesuffix = "";
    if(defined($self->{o32sections}{$copyentry->{ulSource}})) {
        $namesuffix = "_" . $self->{o32sections}{$copyentry->{ulSource}}->{filename} . "-" . $self->{o32sections}{$copyentry->{ulSource}}->{name}
    }

    my $data = $rom->GetVData($copyentry->{ulSource}, $copyentry->{ulCopyLen});

    my $filename = GetUniqueFilename($savedir, sprintf("data_0x%08lx_0x%08lx%s.bin", $copyentry->{ulDest}, ($copyentry->{ulDest} + $copyentry->{ulDestLen}), $namesuffix));

    my $fh= IO::File->new($filename, "w+") or die "$filename: $!\n";
    binmode $fh;
    $fh->print($data);
    $fh->close();
}

# ... these are class methods / static functions

# finds the rom header, which points back to the specified start offset.
sub FindRomHdr {
    my ($rom, $firstofs)= @_;
#   if ($have_xiputils) {
#       return XdaDevelopers::XipUtils::findromhdr($rom->{data}, $firstofs)
#   }
    my $hdrptr= $rom->GetPDword($firstofs+0x44);

    #printf("searching for header at ptr=0x%08lx from ofs=0x%08lx\n", $hdrptr, $firstofs+0x48);
    # search for romheader, starting directly after 'ECEC', until end of rom.
    for(my $hdrofs=$firstofs+0x48 ; $hdrofs < $rom->{size}-0x54 ; $hdrofs+=4)
    {
        my $firstptr= $rom->GetPDword($hdrofs+8);

        if ($hdrptr-$firstptr==$hdrofs-$firstofs) {
            #printf("found romheader at ptr:f=0x%08lx, h=0x%08lx  | ofs:f=0x%08lx, h=0x%08lx\n",
            #    $firstptr, $hdrptr, $firstofs, $hdrofs);

            return $hdrofs;
        }
    }
    return -1;
}
# finds the rom header, which points back to the specified start offset.
# this is optimized by looking for the cpuid
sub FindRomHdrByCpu {
    my $rom= shift;
    my $firstofs= shift;
    my $cpuid= pack("V",shift);
    my $hdrptr= $rom->GetPDword($firstofs+0x44);

    #printf("searching for cpuid in header at ptr=0x%08lx from ofs=0x%08lx\n", $hdrptr, $firstofs+0x48);
    # search for romheader, starting directly after 'ECEC', until end of rom.
    #   ( 0x48 = ofs directly ofter romhdr-ptr, 0x44 is ofs of cpuid in romhdr )
    my $ofs=$rom->find($cpuid, $firstofs+0x48+0x44);
    #   0x10 is size of rest of romhdr of cpuid.
    while ($ofs!=-1 && $ofs < $rom->{size}-0x10)
    {
        my $hdrofs= $ofs-0x44;
        my $firstptr= $rom->GetPDword($hdrofs+8);

        #print unpack("H*", $rom->GetPData($hdrofs, 0x50)), "\n";
        #printf(" cpuid at 0x%08lx  ptr:f=0x%08lx, h=0x%08lx  | ofs:f=0x%08lx, h=0x%08lx\n",
        #    $ofs, $firstptr, $hdrptr, $firstofs, $hdrofs);

        if ($hdrptr-$firstptr==$hdrofs-$firstofs) {
            #printf("found romheader at ptr:f=0x%08lx, h=0x%08lx  | ofs:f=0x%08lx, h=0x%08lx\n",
            #    $firstptr, $hdrptr, $firstofs, $hdrofs);

            return $hdrofs;
        }

        $ofs=$rom->find($cpuid, $ofs+4);
    }
    return -1;
}
sub FindXipBlocks {
    my $rom= shift;

    my $cpuid;
    my @xiplist;
    my $ofs= 0;
    while ($ofs < $rom->{size}) {
        my $ececofs= $rom->find("ECEC", $ofs);
        last if ($ececofs==-1);

        my $firstofs= $ececofs-0x40;
        my $hdrptr= $rom->GetPDword($firstofs+0x44);
        my $hdrofs= $cpuid? FindRomHdrByCpu($rom, $firstofs, $cpuid) : FindRomHdr($rom, $firstofs);
        if ($hdrofs==-1) {
            $ofs= $ececofs+4;
        }
        else {
            my $firstptr= $rom->GetPDword($hdrofs+8);
            my $lastptr= $rom->GetPDword($hdrofs+12);
            $cpuid= $rom->GetPDword($hdrofs+68);
            my $lastofs= $lastptr-$hdrptr+$hdrofs;

            push @xiplist, { ofs=>$firstofs, len=>$lastptr-$firstptr, base=>$firstptr };

            $ofs= $lastofs+0x40;
        }
    }
    #printf("found %d xip blocks\n", scalar @xiplist);

    return \@xiplist;
}

#############################################################################
#############################################################################
package ROM;
use strict;
use Carp;

sub new {
    my $class= shift;
    my $data= shift;
    my $base= shift;
    return bless { data=>$data, size=>length($data) }, $class;
}
sub setbase {
    my ($self, $dataofs, $base)= @_;

    $self->{base}= $base- $dataofs;
}
sub IsInRange {
    my ($self, $ofs)= @_;
    return $ofs-$self->{base}>=0 && $ofs-$self->{base}<$self->{size};
}
sub find {
    my ($self, $str, $ofs)= @_;
    return index($self->{data}, $str, $ofs);
}
sub GetDword {
    my ($self, $ofs)= @_;

    return unpack("V", $self->GetVData($ofs, 4));
}
# get data by virtual offset
sub GetVData {
    my ($self, $ofs, $len)= @_;
    if ($ofs-$self->{base}<0 || $ofs-$self->{base}+$len > length($self->{data})) {
        croak sprintf("0x%08lx l=0x%08lx beyond size : base=0x%08lx l=0x%08lx\n", $ofs, $len, $self->{base}, length($self->{data}));
    }
    return substr($self->{data}, $ofs-$self->{base}, $len)
}
# get data by physical offset
sub GetPData {
    my ($self, $ofs, $len)= @_;
    return substr($self->{data}, $ofs, $len)
}
# get dword by physical offset
sub GetPDword {
    my ($self, $ofs)= @_;
    return unpack("V", $self->GetPData($ofs, 4));
}

sub GetString {
    my ($self, $ofs)= @_;

    if ($ofs==0) {
        return "((null))";
    }

    my $nulpos= $self->{base}+index($self->{data}, "\x00", $ofs-$self->{base});

    return $self->GetVData($ofs, $nulpos-$ofs);
}

#############################################################################
#############################################################################
package MemSpace;
use strict;
use Carp;

sub new {
    return bless {}, shift;
}
sub setvbase {
    my ($self, $physical, $virtual)= @_;

    $self->{base}= $virtual - $physical;

    # virtualaddr = physical + base
}

# add region by virtual address.
sub vadd {
    my ($self, $vstart, $len, $fmt, @args)= @_;

    if ($vstart==0) {
        carp "vadd: v=NULL\n";
        return;
    }

    my $paddr= $vstart-$self->{base};
    push @{$self->{items}{$paddr}}, {
        pstart=>$paddr,
        vstart=>$vstart,
        len=>$len,
        desc=>sprintf($fmt, @args)
    };
}

# fill blanks in virtual region.
sub vfillblanks {
    my ($self, $rom, $first, $last)= @_;
    my $vprev;
    for my $pofs (sort {$a<=>$b} keys %{$self->{items}}) {
        my $vofs= $pofs+$self->{base};
        next if ($vofs<$first);
        last if ($vofs>$last);

        #printf("adding unknown first=0x%08lx last=0x%08lx vofs=0x%08lx vprev=0x%08lx pofs=0x%08lx\n", $first, $last, $vofs, $vprev, $pofs);
        $self->vadd_unknown($rom, $first, $vofs-$first) if (!$vprev && $vofs>$first);
        $self->vadd_unknown($rom, $vprev, $vofs-$vprev) if ($vprev && $vofs>$vprev);
        my $maxlen;
        for my $item (sort {$a->{len}<=>$b->{len}} @{$self->{items}{$pofs}}) {
            $maxlen= $item->{len} if (!defined $maxlen || $maxlen < $item->{len});
        }
        $vprev= $vofs+$maxlen;
    }

    #printf("adding last unknown first=0x%08lx last=0x%08lx vprev=0x%08lx\n", $first, $last, $vprev);
    $self->vadd_unknown($rom, $vprev, $last-$vprev) if ($vprev && $last > $vprev);
}
sub vadd_unknown {
    my ($self, $rom, $start, $len)= @_;
    my $data= $rom->GetVData($start, $len);
    my $desc;
    if ($data =~ /^\x00+$/) {
        $desc= "NUL";
    }
    elsif ($data =~ /^\xff+$/) {
        $desc= "ONE";
    }
    elsif ($data =~ /^...\xea\x00+$/) {
        my $target=unpack("V", $data);
        $desc= sprintf("kernel entry point : branch to 0x%08lx", $start+4*($target&0xffffff)+8);
    }
    else {
        if (length($data)>64) {
            $desc= "unknown-large: ".unpack("H*", substr($data, 0, 64));
        }
        else {
            $desc= "UTV jump instruction block: ".unpack("H*", $data); # EMAC: changed
            #$desc= "unknown: ".unpack("H*", $data);
        }

    }
    #printf("... unknown 0x%08lx-0x%08lx L0x%08lx\n", $start, $start+$len, $len);
    $self->vadd($start, $len, $desc);
}

# functions dealing with physical offsets.
sub padd {
    my ($self, $pstart, $len, $fmt, @args)= @_;

    push @{$self->{items}{$pstart}}, {
        pstart=>$pstart,
        len=>$len,
        desc=>sprintf($fmt, @args)
    };
}

# fill blanks in physical region.
sub pfillblanks {
    my ($self, $rom, $first, $last)= @_;

    my $pprev;
    for my $pofs (sort {$a<=>$b} keys %{$self->{items}}) {
        next if ($pofs<$first);
        last if ($pofs>$last);

        $self->padd_unknown($rom, $first, $pofs-$first) if (!$pprev && $pofs>$first);
        $self->padd_unknown($rom, $pprev, $pofs-$pprev) if ($pprev && $pofs>$pprev);
        my $maxlen;
        for my $item (sort {$a->{len}<=>$b->{len}} @{$self->{items}{$pofs}}) {
            $maxlen= $item->{len} if (!defined $maxlen || $maxlen < $item->{len});
        }
        $pprev= $pofs+$maxlen;
    }

    $self->padd_unknown($rom, $pprev, $last-$pprev) if ($pprev && $last > $pprev);
}
# add unknown region by physical address
sub padd_unknown {
    my ($self, $rom, $start, $len)= @_;
    my $data= $rom->GetPData($start, $len);
    my $desc;
    if ($data =~ /^(\x00*)(\xff*)$/) {
        my $l_nul= length($1);
        my $l_one= length($2);
        #printf("adding NULONE section: 0x%08lx l 0x%08lx\n", $start, $len); ###
        $self->padd($start, $l_nul, "NUL") if ($l_nul);
        $self->padd($start+$l_nul, $l_one, "ONE") if ($l_one);
    }
    else {
        my $bofs= 0;
        pos($data)= $bofs;
        if ($data =~ /\G\x00+/) {
            if (length($&)>16) {
                $self->padd($start+$bofs, length($&), "NUL");
                $bofs += length($&);
            }
        }
        pos($data)= $bofs;
        if ($data =~ /\G\xff+/) {
            if (length($&)>16) {
                #printf("adding ONE section: 0x%08lx l 0x%08lx : 0x%08lx l 0x%08lx\n", $start, $len, $start+$bofs, length($&)); ###
                $self->padd($start+$bofs, length($&), "ONE");
                $bofs += length($&);
            }
        }
        my $eofs= length($data);
        if ($eofs < 0x1000) {
# !!! this regex takes a very long time for large data.
#  .. and the remainder unknown is not calculated correctly
 
            pos($data)= $eofs;
            if ($data =~ /\xff+\G/) {
                if (length($&)>16) {
                    $eofs -= length($&);
                    if ($eofs>$bofs) {
                        $self->padd($start+$eofs, length($&), "ONE");
                    }
                }
            }
            pos($data)= $eofs;
            if ($data =~ /\x00+\G/) {
                if (length($&)>16) {
                    $eofs -= length($&);
                    if ($eofs>$bofs) {
                        $self->padd($start+$eofs, length($&), "NUL");
                    }
                }
            }
        }
        #printf("punknown: start=0x%08lx len=0x%08lx eofs=0x%08lx bofs=0x%08lx\n", $start, $len, $eofs, $bofs);

# removed this restriction:  $len-$bofs==0x2000 && 
        if (substr($data, $bofs+0x48, 4) eq "RSA1") {
            $desc= "xip-chain";
            $self->ParseXipChain(substr($data, $bofs, $eofs-$bofs));
        }
        elsif ($eofs-$bofs>64) {
            $desc= "unknown-large: ".unpack("H*", substr($data, $bofs, 64));
        }
        else {
            $desc= "unknown: ".unpack("H*", substr($data, $bofs, $eofs-$bofs));
        }
        $self->padd($start+$bofs, $eofs-$bofs, $desc) if ($eofs>$bofs);
    }
}
sub ParseXipChainEntry {
    my $xipentry= shift;
    my %xip;
    (
        $xip{pvAddr},
        $xip{dwLength},
        $xip{dwMaxLength},
        $xip{usOrder},
        $xip{usFlags},
        $xip{dwVersion},
        $xip{szName},
        $xip{dwAlgoFlags},
        $xip{dwKeyLen},
        $xip{byPublicKey},
    )= unpack("VVVvvVA32VVa*", $xipentry);
    return \%xip;
}
sub ParseXipChain {
    my $self= shift;
    my $xipchain= shift;
    if (keys %g_xipchaininfo) {
        printf("!!! found multiple xip-chains - appending\n");
    }
    my $nrxips= unpack("V", $xipchain);
    for (my $i=0 ; $i<$nrxips ; $i++) {
        my $xip= ParseXipChainEntry(substr($xipchain, 4+0x290*$i, 0x290));
        $self->vadd($xip->{pvAddr}, 0, sprintf("xip block 0x%08lx-0x%08lx '%s'", $xip->{pvAddr}, $xip->{pvAddr}+$xip->{dwLength}, $xip->{szName}));

        if (exists $g_xipchaininfo{$xip->{pvAddr}}) {
            printf("!!! xipchain contains duplicate address: 0x%08lx\n", $xip->{pvAddr});
        }
        $g_xipchaininfo{$xip->{pvAddr}}= $xip;
    }
    if (substr($xipchain, 4+0x290*$nrxips) !~ /^\x00+$/) {
        printf("!!! xip chain padded with non-null\n");
    }
}
sub print {
    my $self= shift;
    my $prev;
    for my $pofs (sort {$a<=>$b} keys %{$self->{items}}) {
        if ($prev && $pofs>$prev) {
            printf("0x%08lx-0x%08lx L0x%08lx  unknown\n", $prev, $pofs, $pofs-$prev);
        }
        elsif ($prev && $pofs<$prev) {
            printf("0x%08lx-0x%08lx L0x%08lx  overlap!!\n", $pofs, $prev, $prev-$pofs);
        }
        my $maxlen;
        for my $item (sort {$a->{len}<=>$b->{len}} @{$self->{items}{$pofs}}) {
            $maxlen= $item->{len} if (!defined $maxlen || $maxlen < $item->{len});

            # ... not printing information from blanks.
            if ($item->{desc} eq "NUL" || $item->{desc} eq "ONE") {
                next;
            }

            if (exists $item->{vstart}) {
                printf("0x%08lx-0x%08lx | 0x%08lx-0x%08lx L0x%08lx %s\n", 
                    $item->{pstart}, $item->{pstart}+$item->{len},
                    $item->{vstart}, $item->{vstart}+$item->{len},
                    $item->{len}, $item->{desc});
            }
            else {
                printf("0x%08lx-0x%08lx  L0x%08lx %s\n", 
                    $item->{pstart}, $item->{pstart}+$item->{len},
                    $item->{len}, $item->{desc});
            }
        }
        $prev= $pofs+$maxlen;
    }
}

#############################################################################
#############################################################################
package ExeFile;
use strict;
use Carp;

sub new {
    my ($class, $cputype, $timestamp)= @_;

    my %sections = (); # EMAC: added to detect duplicate sections.

    return bless {
        cputype=>$cputype,
        timestamp=>$timestamp,
        sections=>\%sections
    }, $class;
}
sub addo32 {
    my ($self, $o32)= @_;
    push @{$self->{o32rom}}, $o32;
}
sub adde32 {
    my ($self, $e32)= @_;
    $self->{e32rom}= $e32;
}
sub save_data {
    my ($filename, $data)= @_;
    my $fh= IO::File->new($filename, "w") or die "$filename: $!\n";
    binmode $fh;
    $fh->print($data);
    $fh->close();
}

sub SaveToFile {
    my ($self, $fn)= @_;

    my ($exedata, $peexe)= $self->reconstruct_binary(); # EMAC: Added $peexe for copy entry info comparison for the UTV

    save_data($fn, $exedata);

    return $peexe; # EMAC: Added for copy entry info comparison for the UTV
}

sub pack_mz_header {
    return pack("H*", "4d5a90000300000004000000ffff0000").
           pack("H*", "b8000000000000004000000000000000").
           pack("H*", "00000000000000000000000000000000").
           pack("H*", "000000000000000000000000c0000000").
           pack("H*", "0e1fba0e00b409cd21b8014ccd215468").
           pack("H*", "69732070726f6772616d2063616e6e6f").
           pack("H*", "742062652072756e20696e20444f5320").
           pack("H*", "6d6f64652e0d0d0a2400000000000000").
           pack("H*", "00000000000000000000000000000000"). # EMAC: Added extra padding to match UTV
           pack("H*", "00000000000000000000000000000000").
           pack("H*", "00000000000000000000000000000000").
           pack("H*", "00000000000000000000000000000000");

}
sub pack_e32exe {
    my ($e32exe)= @_;

    my @info= qw(EXP IMP RES EXC SEC FIX DEB IMD MSP TLS CBK RS1 RS2 RS3 RS4 RS5);

    return pack("a4vvVVVvvvCCVV8v6V4v2V6",
            $e32exe->{magic}, 
            $e32exe->{cpu}, 
            $e32exe->{objcnt}, 
            $e32exe->{timestamp}, 
            $e32exe->{symtaboff}, 

            $e32exe->{symcount}, 
            $e32exe->{opthdrsize}, 
            $e32exe->{imageflags}, 
            $e32exe->{coffmagic}, 
            $e32exe->{linkmajor}, 
            $e32exe->{linkminor}, 
            $e32exe->{codesize}, 

            $e32exe->{initdsize}, 
            $e32exe->{uninitdsize}, 
            $e32exe->{entryrva}, 
            $e32exe->{codebase}, 

            $e32exe->{database}, 
            $e32exe->{vbase}, 
            $e32exe->{objalign}, 
            $e32exe->{filealign}, 

            $e32exe->{osmajor}, 
            $e32exe->{osminor}, 
            $e32exe->{usermajor}, 
            $e32exe->{userminor}, 
            $e32exe->{subsysmajor}, 
            $e32exe->{subsysminor}, 
            $e32exe->{res1}, 

            $e32exe->{vsize}, 
            $e32exe->{hdrsize}, 
            $e32exe->{filechksum}, 
            $e32exe->{subsys}||0x09, # EMAC: change for UTV 
            $e32exe->{dllflags}, 

            $e32exe->{stackmax}, 
            $e32exe->{stackinit}, 
            $e32exe->{heapmax}, 
            $e32exe->{heapinit}, 

            $e32exe->{res2}, 
            $e32exe->{hdrextra}, 
    ).  join("", map { pack("VV", $e32exe->{"${_}_rva"}||0, $e32exe->{"${_}_size"}||0) } @info);

}
sub pack_o32obj {
    my ($o32obj)= @_;

    return pack("a8V8",
        $o32obj->{name},
        $o32obj->{vsize}, 
        $o32obj->{rva}, 
        $o32obj->{psize}, 
        $o32obj->{dataptr}, 
        $o32obj->{realaddr}, 
        $o32obj->{access}, 
        $o32obj->{temp3}, 
        $o32obj->{flags});
}
sub IMAGE_FILE_RELOCS_STRIPPED { 1 };
sub IMAGE_SCN_COMPRESSED               { 0x00002000 }
#sub IMAGE_SCN_CNT_CODE                 { 0x00000020 }
#sub IMAGE_SCN_CNT_INITIALIZED_DATA     { 0x00000040 }
#sub IMAGE_SCN_CNT_UNINITIALIZED_DATA   { 0x00000080 }
sub IMAGE_SCN_CNT_CODE                 { 0x00000020 } # EMAC: Changed for UTV
sub IMAGE_SCN_CNT_INITIALIZED_DATA     { 0xC0000040 } # EMAC: Changed for UTV
sub IMAGE_SCN_CNT_UNINITIALIZED_DATA   { 0x40000040 } # EMAC: Changed for UTV
sub IMAGE_SCN_CNT_SHARED               { 0xD0000040 } # EMAC: Added for UTV
sub STD_EXTRA    {  16 }
sub IMAGE_FILE_MACHINE_ARM  { 0x01c0 }

sub FindFirstSegment {
    my ($segtypeflag, @o32rom)= @_;
    for my $o32ent (@o32rom) {
        if ($o32ent->{flags} & $segtypeflag) {
            return $o32ent->{rva};
        }
    }
    return 0;
}
sub CalcSegmentSizeSum {
    my ($segtypeflag, @o32rom)= @_;
    my $size= 0;
    for my $o32ent (@o32rom) {
        # vsize is not entirely correct, I should use the uncompressed size,
        # but, I don't know that here yet.
        if (($o32ent->{flags}&$segtypeflag)==$segtypeflag) {
            $size += $o32ent->{vsize};
        }
    }

    return $size;
}
sub round_to_page {
    my ($val, $page)= @_;

    if ($val%$page) {
        return (int($val/$page)+1)*$page;
    }
    return $val;
}
sub round_padding {
    my ($val, $page)= @_;
    if ($val%$page) {
        return $page - ($val%$page);
    }
    return 0;
}

sub convert_e32rom_to_e32exe {
    my ($cputype, $timestamp, $e32rom, @o32rom)= @_;
    my %e32exe;
    $e32exe{magic}= "PE";
    $e32exe{cpu}= $cputype;
    $e32exe{objcnt}= $e32rom->{objcnt};
    $e32exe{timestamp}= $e32rom->{timestamp}||$timestamp||0;
    $e32exe{symtaboff}=0;
    $e32exe{symcount}=0;
    $e32exe{opthdrsize}= 0xe0;   # fixed.
    $e32exe{imageflags}= $e32rom->{imageflags};
    if(($e32rom->{FIX_rva} == 0 || $e32rom->{FIX_size} == 0)) { # EMAC: sometimes the .reloc section rva and size are defined in the utv but not data is available for it in the ROM
        $e32exe{imageflags} |= IMAGE_FILE_RELOCS_STRIPPED;
    }
    $e32exe{coffmagic}= 0x10b;
    $e32exe{linkmajor}= 6;
    $e32exe{linkminor}= 1;
    $e32exe{codesize}= CalcSegmentSizeSum(IMAGE_SCN_CNT_CODE, @o32rom);
    $e32exe{initdsize}= CalcSegmentSizeSum(IMAGE_SCN_CNT_INITIALIZED_DATA, @o32rom);
    $e32exe{uninitdsize}= CalcSegmentSizeSum(IMAGE_SCN_CNT_UNINITIALIZED_DATA, @o32rom);
    $e32exe{entryrva}= $e32rom->{entryrva};
    $e32exe{codebase}= FindFirstSegment(IMAGE_SCN_CNT_CODE, @o32rom);
    $e32exe{database}= FindFirstSegment(IMAGE_SCN_CNT_INITIALIZED_DATA, @o32rom);
    $e32exe{vbase}= $e32rom->{vbase};
    $e32exe{objalign}= 0x1000;
    $e32exe{filealign}= 0x200;
    $e32exe{osmajor}= 4;
    $e32exe{osminor}= 0;
    $e32exe{usermajor}= 0;
    $e32exe{userminor}= 0;
    $e32exe{subsysmajor}= $e32rom->{subsysmajor}||0;
    $e32exe{subsysminor}= $e32rom->{subsysminor}||0;
    $e32exe{res1}= 0;   # 'Win32 version' according to dumpbin
    $e32exe{vsize}= $e32rom->{vsize};
    #$e32exe{hdrsize}= round_to_page(0x80+0xf8+@o32rom*0x28, $e32exe{filealign});
    $e32exe{hdrsize}= round_to_page(0xC0+0xf8+@o32rom*0x28, $e32exe{filealign}); # EMAC: changed for UTV

    $e32exe{filechksum}= 0;
    $e32exe{subsys}= $e32rom->{subsys};
    $e32exe{dllflags}= $e32rom->{dllflags}||0;
    $e32exe{stackmax}= $e32rom->{stackmax};
    $e32exe{stackinit}=0x1000; # ?
    $e32exe{heapmax}=0x100000; # ?
    $e32exe{heapinit}=0x1000;  # ?

    $e32exe{res2}= 0;      # 'loader flags' according to dumpbin
    $e32exe{hdrextra}= STD_EXTRA;   # nr of directories

    $e32exe{EXP_rva}= $e32rom->{EXP_rva}; $e32exe{EXP_size}= $e32rom->{EXP_size};
    $e32exe{IMP_rva}= $e32rom->{IMP_rva}; $e32exe{IMP_size}= $e32rom->{IMP_size};
    $e32exe{RES_rva}= $e32rom->{RES_rva}; $e32exe{RES_size}= $e32rom->{RES_size};
    $e32exe{EXC_rva}= $e32rom->{EXC_rva}; $e32exe{EXC_size}= $e32rom->{EXC_size};
    $e32exe{SEC_rva}= $e32rom->{SEC_rva}; $e32exe{SEC_size}= $e32rom->{SEC_size}; # always 0

    # relocation info is always missing
    $e32exe{FIX_rva}= $e32rom->{FIX_rva}; $e32exe{FIX_size}= $e32rom->{FIX_size};

    # $e32exe{DEB_rva}= $e32rom->{DEB_rva}; $e32exe{DEB_size}= $e32rom->{DEB_size};
    $e32exe{IMD_rva}= $e32rom->{IMD_rva}; $e32exe{IMD_size}= $e32rom->{IMD_size}; # always 0
    $e32exe{MSP_rva}= $e32rom->{MSP_rva}; $e32exe{MSP_size}= $e32rom->{MSP_size}; # always 0

    $e32exe{RS4_rva}= $e32rom->{sect14rva}; $e32exe{RS4_size}= $e32rom->{sect14size};

    return \%e32exe;
}
sub convert_o32rom_to_o32obj {
    my ($perom, $o32rom, $e32rom)= @_;

    my $segtype;
    if ($e32rom->{RES_rva} == $o32rom->{rva} && $e32rom->{RES_size} == $o32rom->{vsize}) {
        $segtype= ".rsrc";
    }
    elsif ($e32rom->{EXC_rva} == $o32rom->{rva} && $e32rom->{EXC_size} == $o32rom->{vsize}) {
        $segtype= ".pdata";
    }
    elsif ($e32rom->{FIX_rva} == $o32rom->{rva} && $e32rom->{FIX_size} == $o32rom->{vsize}) { # EMAC: added for UTV
        $segtype= ".reloc";
    }
    elsif ($o32rom->{flags}&IMAGE_SCN_CNT_CODE) {
        $segtype= ".text";
    }
    elsif ($o32rom->{flags} == IMAGE_SCN_CNT_INITIALIZED_DATA) { # EMAC: Changed for UTV
        $segtype= ".data";
    }
    elsif ($o32rom->{flags} == IMAGE_SCN_CNT_UNINITIALIZED_DATA) { # EMAC: Changed for UTV
        $segtype= ".pdata";

        if(defined($perom->{sections}->{$segtype}) && !defined($perom->{sections}->{".rsrc"})) { # EMAC: use .resc for the second .pdata
            $segtype = ".rsrc";
        }
    }
    elsif ($o32rom->{flags} == IMAGE_SCN_CNT_SHARED) { # EMAC: Added for UTV
        $segtype= ".shared";
    }
    else {
        $segtype= ".other";
    }

    if(defined($perom->{sections}->{$segtype})) { # EMAC: If there's duplicate sections, rename
        $perom->{sections}->{$segtype}++;

        $segtype = substr($segtype, 0, -1) . $perom->{sections}->{$segtype};
    } else {
        $perom->{sections}->{$segtype} = 1;
    }

    my %o32obj;

    # todo: add sequence nrs to identically named sections
    $o32obj{name} = $segtype;
    $o32obj{vsize}= $o32rom->{vsize};
    $o32obj{rva}  = $g_use_wince3_compression
        ? $o32rom->{rva}
        : (($o32rom->{realaddr}||$o32rom->{dataptr}) - $e32rom->{vbase});
    $o32obj{psize}= $o32rom->{psize};
    $o32obj{psize}= length($o32rom->{data}) if (length($o32rom->{data}) > $o32rom->{psize});
    $o32obj{odataptr} = $o32rom->{dataptr}; # EMAC: added for the UTV
    $o32obj{dataptr}= 0;  # *** set at a later moment
    $o32obj{realaddr}= 0; # file pointer to relocation table
    $o32obj{access}= 0;   # file pointer to line numbers
    $o32obj{temp3}= 0;    # number of relocations + number of line numbers
    $o32obj{flags}= $o32rom->{flags} & ~IMAGE_SCN_COMPRESSED;

    return \%o32obj;
}

sub convert_rom_to_exe {
    my ($perom)= @_;

    my %peexe;
    $peexe{e32exe}= convert_e32rom_to_e32exe($perom->{cputype}, $perom->{timestamp}, $perom->{e32rom}, @{$perom->{o32rom}});

    # EMAC: even though the .reloc section is stripped from the ROM, the UTV will crash without the rva and vsize
    if(($peexe{e32exe}->{FIX_rva} > 0 && $peexe{e32exe}->{FIX_size} > 0) && $g_addblankreloctable) { 
        my $has_reloc_data = 0;
        for my $o32ent (@{$perom->{o32rom}}) {
            if ($peexe{e32exe}->{FIX_rva} == $o32ent->{rva} && $peexe{e32exe}->{FIX_size} == $o32ent->{vsize}) {
                $has_reloc_data = 1;
                last;
            }
        }
        if(!$has_reloc_data) {
            push @{$perom->{o32rom}}, {
                "rva" => $peexe{e32exe}->{FIX_rva},
                "vsize" => $peexe{e32exe}->{FIX_size},
                "psize" => 0,
                "dataptr" => 0,
                "flags" => 0x40000042,
                "data" => ""
            };
            $peexe{e32exe}->{objcnt}++;
        } else {
            #$peexe{e32exe}->{imageflags} |= IMAGE_FILE_RELOCS_STRIPPED;
        }
    }
    
    my $fileofs= $peexe{e32exe}{hdrsize};
    for my $o32ent (@{$perom->{o32rom}}) {
        my $o32obj= convert_o32rom_to_o32obj($perom, $o32ent, $perom->{e32rom});
        push @{$peexe{o32obj}}, $o32obj;

        if($o32obj->{psize} > 0) { # EMAC: changed for UTV .reloc
            $o32obj->{dataptr}= $fileofs;

            $peexe{rvamap}{$o32ent->{rva}}= { rva=>$o32obj->{rva}, size=>$o32obj->{vsize} };

            $fileofs += round_to_page($o32obj->{psize}, $peexe{e32exe}{filealign});
        }
    }


    return \%peexe;
}
sub RvaToFileOfs {
    my ($rva, @o32obj)= @_;
    for my $o32ent (@o32obj) {
        if ($o32ent->{rva}<=$rva && $rva < $o32ent->{rva} + $o32ent->{vsize}) {
            return $o32ent->{dataptr}+$rva-$o32ent->{rva};
        }
    }
}
sub strread_dword {
    my ($pstr, $ofs)= @_;
    return unpack("V", substr($$pstr, $ofs, 4));
}
sub strwrite_dword {
    my ($pstr, $ofs, $dword)= @_;
    substr($$pstr, $ofs, 4)= pack("V", $dword);
}

# rvamap maps romrva's to objrva's
sub find_rva_patch {
    my ($objrva, $rvamap)= @_;
        #$peexe{rvamap}{$_->{rva}}= { rva=>$o32obj->{rva}, size=>$o32obj->{vsize} };
    for my $romrva (keys %$rvamap) {
        my $info= $rvamap->{$romrva};
        if ($romrva <= $objrva && $objrva < $romrva+$info->{size}) {
            return $objrva-$romrva+$info->{rva};
        }
    }
    return $objrva;
}

sub repair_table {
    my ($table_rva, $peexe, $pstr)= @_;

    my $impofs= RvaToFileOfs($table_rva, @{$peexe->{o32obj}});
    while (1) {
        my $impaddr= strread_dword($pstr, $impofs+0x10);
        last if ($impaddr==0);

        my $newimpaddr = find_rva_patch($impaddr, $peexe->{rvamap});

        strwrite_dword($pstr, $impofs+0x10, $newimpaddr);

        $impofs += 0x14;
    }
}

sub reconstruct_binary {
    my ($file)= @_;

    my $peexe= $file->convert_rom_to_exe();

    my $mz_data = pack_mz_header();
    # $file->{sections}[$i]{data}  contains the section data

    my $e32exe_data = pack_e32exe($peexe->{e32exe});
    my @o32exe_data = map { pack_o32obj($_) } @{$peexe->{o32obj}};

    my $image= $mz_data;
    $image .= $e32exe_data;
    $image .= $_ for (@o32exe_data);

    # page to filealign
    $image .= "\x00" x ($peexe->{e32exe}{hdrsize} - length($image));

    for my $o32ent (@{$file->{o32rom}}) {
        if(length($o32ent->{data})) { # EMAC: don't check o32 data if data isn't available. Used for the missing .reloc in UTV builds.
            $image .= $o32ent->{data};
            $image .= "\x00" x round_padding(length($o32ent->{data}), $peexe->{e32exe}{filealign});
        }
    }
    
    # repair import table.; EMAC: removing for the UTV
    #repair_table($peexe->{e32exe}{IMP_rva}, $peexe, \$image);

    return $image, $peexe; # EMAC: Added $peexe for copy entry info comparison for the UTV
}

