FROM eclipse-mosquitto:2

COPY entrypoint.sh /mosquitto/entrypoint.sh
RUN sed -i 's/\r$//' /mosquitto/entrypoint.sh && chmod +x /mosquitto/entrypoint.sh

ENTRYPOINT ["/mosquitto/entrypoint.sh"]
CMD ["/usr/sbin/mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]
