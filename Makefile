PREFIX ?= /usr/local
SYSCONFDIR ?= /etc

.PHONY: install uninstall

install:
	@echo "Installing Bosgame M5 Fan Control..."
	install -Dm755 bosgame-fan-control.py $(DESTDIR)$(PREFIX)/bin/bosgame-fan-control
	install -Dm755 fan-control.sh $(DESTDIR)$(PREFIX)/bin/fan-control.sh
	install -Dm644 bosgame-fan-control.conf $(DESTDIR)$(SYSCONFDIR)/bosgame-fan-control.conf
	install -Dm644 bosgame-fan-control.service $(DESTDIR)$(SYSCONFDIR)/systemd/system/bosgame-fan-control.service
	install -Dm644 bosgame-fan-control.desktop $(DESTDIR)/usr/share/applications/bosgame-fan-control.desktop
	@echo ""
	@echo "Installation complete!"
	@echo ""
	@echo "Enable autostart with:"
	@echo "  sudo systemctl enable --now bosgame-fan-control.service"
	@echo ""
	@echo "Start GUI with:"
	@echo "  bosgame-fan-control"

uninstall:
	@echo "Uninstalling Bosgame M5 Fan Control..."
	rm -f $(DESTDIR)$(PREFIX)/bin/bosgame-fan-control
	rm -f $(DESTDIR)$(PREFIX)/bin/fan-control.sh
	rm -f $(DESTDIR)$(SYSCONFDIR)/bosgame-fan-control.conf
	rm -f $(DESTDIR)$(SYSCONFDIR)/systemd/system/bosgame-fan-control.service
	rm -f $(DESTDIR)/usr/share/applications/bosgame-fan-control.desktop
	@echo "Uninstallation complete!"
