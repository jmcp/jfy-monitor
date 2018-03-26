#!/usr/sbin/dtrace -Cs

#include <sys/termios.h>

pid$target::tcsetattr:entry{
	terms = (struct termios *)copyin((uintptr_t)arg2,
	   sizeof (struct termios));
	printf("\niflag 0x%x\noflag 0x%x\ncflag 0x%x\nlflag 0x%x",
	    terms->c_iflag,
	    terms->c_oflag,
	    terms->c_cflag,
	    terms->c_lflag);
}
