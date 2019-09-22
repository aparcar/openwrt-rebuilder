FROM registry.salsa.debian.org/reproducible-builds/diffoscope:latest

RUN apt-get update -qq &&\
    apt-get install -y \
        build-essential \
        curl \
        file \
        gawk \
        gettext \
        git \
        libncurses5-dev \
        libssl-dev \
        python2.7 \
        python3 \
        python3-pystache \
        rsync \
        subversion \
        sudo \
        swig \
        unzip \
        wget \
        zlib1g-dev \
        && apt-get -y autoremove \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*

RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
RUN useradd -c "OpenWrt ReBuilder" -m -d /builder/shared-workdir/ -G sudo -s /bin/bash build

USER build
ENV HOME /builder/shared-workdir/
WORKDIR /builder/shared-workdir/
ENTRYPOINT []
