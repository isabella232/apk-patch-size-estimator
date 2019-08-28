import mmap

END_OF_CENTRAL_DIRECTORY_SIG = 0x06054b50
CENTRAL_FILE_HEADER = 0x02014b50

# https://pkware.cachefly.net/webdocs/APPNOTE/APPNOTE-6.3.3.TXT


def little_endian(x):
    result = ""
    while x != 0:
        result += chr(x & 0xff)
        x >>= 8
    return result


def little_endian_rev(s):
    num = 0
    while s:
        num <<= 8
        num += ord(s[-1])
        s = s[:-1]
    return num


assert (little_endian_rev(
    little_endian(END_OF_CENTRAL_DIRECTORY_SIG)) == END_OF_CENTRAL_DIRECTORY_SIG
       )


class ZipEntry(object):

    def __init__(self, filename, offset):
        self.filename = filename
        self.offset = offset

    def __repr__(self):
        return "File %s at %s\n" % (self.filename, self.offset)


class Zip(object):

    def __init__(self, filename):
        zip_file = open(filename, 'r+b')
        self.buffer = mmap.mmap(zip_file.fileno(), 0)

    def read_int(self, pos, size=4):
        return little_endian_rev(self.buffer[pos:pos + size])

    def get_entries(self):
        central_dir_offset = self.get_central_dir_offset()
        assert (self.read_int(central_dir_offset) == CENTRAL_FILE_HEADER)

        entries = []
        pos = central_dir_offset
        while self.read_int(pos) == CENTRAL_FILE_HEADER:
            pos += 28
            filename_length = self.read_int(pos, size=2)
            pos += 2
            extra_field_length = self.read_int(pos, size=2)
            pos += 2
            file_comment_length = self.read_int(pos, size=2)
            pos += 10
            offset = self.read_int(pos)
            pos += 4
            filename = self.buffer[pos:pos + filename_length]
            entries.append(ZipEntry(filename, offset))
            pos += filename_length + extra_field_length + file_comment_length
        return entries

    def get_central_dir_offset(self):
        start = len(self.buffer) - 4
        while self.buffer[start:start + 4] != little_endian(
                END_OF_CENTRAL_DIRECTORY_SIG) and start >= 0:
            start -= 1

        start += 10
        print "Total number of records: %s" % self.read_int(start, size=2)
        start += 6
        return little_endian_rev(self.buffer[start:start + 4])


if __name__ == "__main__":
    z = Zip("../gmscore/com.google.android.gms-16896061.apk")
    print z.get_central_dir_offset()
    print sorted(z.get_entries(), key=lambda entry: entry.offset)[:10]
