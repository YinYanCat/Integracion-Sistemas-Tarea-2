# Tests unitarios

## Comando

```bash
python -m unittest discover -s test -v
```

## Resultado

```text
Ran 40 tests in 0.178s

OK
```

## Tests ejecutados (40)

- `test_agregacion`: `test_armar_respuesta_agrega_cuatro_servicios`,
  `test_fallo_de_una_dependencia_no_tumba_la_respuesta`,
  `test_pendiente_usa_payload_de_la_saga_sin_despacho` (3).
- `test_bd_despacho`: `test_cancelar_es_idempotente`,
  `test_crear_repetido_no_duplica` (2).
- `test_bd_stock_idempotencia`: `test_liberar_repetido_no_repone_dos_veces`,
  `test_reservar_repetido_no_descuenta_dos_veces` (2).
- `test_limitador`: `test_limitador_bloquea_exceso`,
  `test_limitador_concurrente_no_supera_el_limite`,
  `test_limitador_es_por_cliente` (3).
- `test_orquestador_bd`: `test_actualizar_cambia_estado_y_pasos`,
  `test_iniciar_es_idempotente_y_guarda_payload` (2).
- `test_orquestador_clientes`: `test_estado_despacho_distingue_no_existe_cancelado_y_indeterminado`,
  `test_reserva_con_rpc_error_marca_error_y_no_exito`,
  `test_bulkhead_lleno_hace_fallback_sin_llamar_a_receta`,
  `test_instantanea_y_reinicio_del_circuito`,
  `test_timeout_de_receta_se_contabiliza_y_degrada`,
  `test_tres_fallos_abren_circuito_y_evitan_nuevas_llamadas`,
  `test_validar_receta_ok_contabiliza_llamada_y_exito` (7).
- `test_orquestador_resiliencia_api`: `test_get_admin_resiliencia_devuelve_estado_y_contadores`,
  `test_post_reset_reinicia_la_resiliencia`, `test_salud_no_cambia` (3).
- `test_resiliencia`: `test_limita_concurrencia_y_libera_permiso`,
  `test_reiniciar_y_liberar_no_bajan_de_cero`,
  `test_fallo_en_medio_abierto_reabre_y_cancelar_libera_la_sonda`,
  `test_medio_abierto_solo_permite_una_sonda_y_exito_cierra`,
  `test_reiniciar_vuelve_a_cerrado`,
  `test_se_abre_tras_tres_fallos_y_bloquea_nuevas_llamadas`,
  `test_contadores_empiezan_en_cero_y_devuelven_copia` (7).
- `test_saga`: `test_camino_feliz`,
  `test_fallo_compensacion_queda_pendiente_de_compensacion_y_reanuda`,
  `test_fallo_despacho_compensa`, `test_reanudar_estado_terminal_no_reanuda`,
  `test_reanudar_no_reserva_dos_veces`, `test_receta_timeout_queda_pendiente`,
  `test_replay_mismo_id_estado_terminal`,
  `test_reserva_error_queda_pendiente_y_reanuda_reservando`,
  `test_stock_insuficiente_falla_sin_despacho`,
  `test_timeout_despacho_estado_indeterminado_queda_pendiente`,
  `test_timeout_despacho_pero_creado_no_compensa` (11).

Total: 3 + 2 + 2 + 3 + 2 + 7 + 3 + 7 + 11 = 40 tests, todos OK.

La salida incluye logs esperados de WARNING de resiliencia (fallbacks, circuito abierto),
que corresponden a escenarios inducidos por los propios tests y no son fallos.
