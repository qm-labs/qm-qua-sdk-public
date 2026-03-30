from qm.grpc.octave.v1 import api_pb2


def default_explore_response() -> api_pb2.ExploreResponse:
    return api_pb2.ExploreResponse(
        modules=[
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER, index=1),
                id="0025_F",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER, index=2),
                id="0024_F",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER, index=3),
                id="01170A01F2226006012",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER, index=4),
                id="0027_F",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_RF_UPCONVERTER, index=5),
                id="01170A01F2215017712",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_RF_DOWNCONVERTER, index=1),
                id="2",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_RF_DOWNCONVERTER, index=2),
                id="3",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_IF_DOWNCONVERTER, index=1),
                id="0005_A",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_IF_DOWNCONVERTER, index=2),
                id="0007_A",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER, index=3),
                id="0008_B",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER, index=4),
                id="22150030_B",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER, index=5),
                id="0010_B",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_SYNTHESIZER, index=6),
                id="22150023_B",
            ),
            api_pb2.ExploreResponse.ModuleId(
                module=api_pb2.ModuleReference(type=api_pb2.OctaveModule.OCTAVE_MODULE_MOTHERBOARD, index=1)
            ),
        ]
    )


def default_identify_response() -> api_pb2.IdentifyResponse:
    rf_up_converters = [
        api_pb2.RFUpConvIdentity(
            index=1,
            connectivity=api_pb2.RFUpConvIdentity.Connectivity(
                i_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(i_index=1)),
                q_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(q_index=1)),
                lo_input=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=3, output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_MAIN
                    )
                ),
            ),
            parameters=api_pb2.RFUpConvIdentity.Parameters(attn_1_db=0, attn_2_db=0),
        ),
        api_pb2.RFUpConvIdentity(
            index=2,
            connectivity=api_pb2.RFUpConvIdentity.Connectivity(
                i_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(i_index=2)),
                q_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(q_index=2)),
                lo_input=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=6,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_SECONDARY,
                    )
                ),
            ),
            parameters=api_pb2.RFUpConvIdentity.Parameters(attn_1_db=0, attn_2_db=0),
        ),
        api_pb2.RFUpConvIdentity(
            index=3,
            connectivity=api_pb2.RFUpConvIdentity.Connectivity(
                i_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(i_index=3)),
                q_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(q_index=3)),
                lo_input=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=6, output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_MAIN
                    )
                ),
            ),
            parameters=api_pb2.RFUpConvIdentity.Parameters(attn_1_db=0, attn_2_db=0),
        ),
        api_pb2.RFUpConvIdentity(
            index=4,
            connectivity=api_pb2.RFUpConvIdentity.Connectivity(
                i_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(i_index=4)),
                q_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(q_index=4)),
                lo_input=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=5,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_SECONDARY,
                    )
                ),
            ),
            parameters=api_pb2.RFUpConvIdentity.Parameters(attn_1_db=0, attn_2_db=0),
        ),
        api_pb2.RFUpConvIdentity(
            index=5,
            connectivity=api_pb2.RFUpConvIdentity.Connectivity(
                i_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(i_index=5)),
                q_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(q_index=5)),
                lo_input=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=5, output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_MAIN
                    )
                ),
            ),
            parameters=api_pb2.RFUpConvIdentity.Parameters(attn_1_db=0, attn_2_db=0),
        ),
    ]

    rf_down_converters = [
        api_pb2.RFDownConvIdentity(
            index=1,
            connectivity=api_pb2.RFDownConvIdentity.Connectivity(
                # debug_rf_input_1=None,
                # debug_rf_input_2=None,
                # debug_rf_input_3=None,
                # debug_rf_input_4=None,
                # debug_rf_input_5=None,
                rf_main_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(rf_in_index=1)),
                lo_input_1=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=4,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_SECONDARY,
                    )
                ),
                lo_input_2=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=3,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_SECONDARY,
                    ),
                ),
            ),
        ),
        api_pb2.RFDownConvIdentity(
            index=2,
            connectivity=api_pb2.RFDownConvIdentity.Connectivity(
                debug_rf_input_1=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=1)),
                debug_rf_input_2=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=2)),
                debug_rf_input_3=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=3)),
                debug_rf_input_4=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=4)),
                debug_rf_input_5=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=5)),
                rf_main_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(rf_in_index=2)),
                lo_input_1=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=4,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_MAIN,
                    )
                ),
                lo_input_2=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=4,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_SYNTH,
                    ),
                ),
            ),
        ),
    ]

    if_down_converters = [
        api_pb2.IFDownConvIdentity(
            index=1,
            connectivity=api_pb2.IFDownConvIdentity.Connectivity(
                channel_1_input=api_pb2.IFSource(
                    rf_downconv_if_source=api_pb2.RFDownConvIFSource(
                        index=1, output_port=api_pb2.RFDownConvIFSource.OutputPort.OUTPUT_PORT_I
                    )
                ),
                channel_1_lo_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(if_lo_i_index=1)),
                channel_2_input=api_pb2.IFSource(
                    rf_downconv_if_source=api_pb2.RFDownConvIFSource(
                        index=1, output_port=api_pb2.RFDownConvIFSource.OutputPort.OUTPUT_PORT_Q
                    )
                ),
                channel_2_lo_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(if_lo_q_index=1)),
            ),
        ),
        api_pb2.IFDownConvIdentity(
            index=2,
            connectivity=api_pb2.IFDownConvIdentity.Connectivity(
                channel_1_input=api_pb2.IFSource(
                    rf_downconv_if_source=api_pb2.RFDownConvIFSource(
                        index=2, output_port=api_pb2.RFDownConvIFSource.OutputPort.OUTPUT_PORT_I
                    )
                ),
                channel_1_lo_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(if_lo_i_index=2)),
                channel_2_input=api_pb2.IFSource(
                    rf_downconv_if_source=api_pb2.RFDownConvIFSource(
                        index=2, output_port=api_pb2.RFDownConvIFSource.OutputPort.OUTPUT_PORT_Q
                    )
                ),
                channel_2_lo_input=api_pb2.IFSource(external_if_input=api_pb2.ExternalIFInput(if_lo_q_index=2)),
            ),
        ),
    ]

    synthesizers = [
        api_pb2.SynthIdentity(
            index=3,
            connectivity=api_pb2.SynthIdentity.Connectivity(
                main_lo_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(lo_input_index=1)),
                secondary_lo_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(demod_lo_input_index=1)),
            ),
            parameters=api_pb2.SynthIdentity.Parameters(
                low_frequency_filters=[
                    api_pb2.SynthIdentity.Parameters.LowFrequencyFilter(index=0, filter_1="1", filter_2="2")
                ],
                medium_frequency_filter=api_pb2.SynthIdentity.Parameters.ParametrizedFilter(),
                high_frequency_filter=api_pb2.SynthIdentity.Parameters.ParametrizedFilter(),
            ),
        ),
        api_pb2.SynthIdentity(
            index=6,
            connectivity=api_pb2.SynthIdentity.Connectivity(
                main_lo_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(lo_input_index=3)),
                secondary_lo_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(lo_input_index=2)),
            ),
            parameters=api_pb2.SynthIdentity.Parameters(
                low_frequency_filters=[
                    api_pb2.SynthIdentity.Parameters.LowFrequencyFilter(index=0, filter_1="1", filter_2="2")
                ],
                medium_frequency_filter=api_pb2.SynthIdentity.Parameters.ParametrizedFilter(),
                high_frequency_filter=api_pb2.SynthIdentity.Parameters.ParametrizedFilter(),
            ),
        ),
        api_pb2.SynthIdentity(
            index=5,
            connectivity=api_pb2.SynthIdentity.Connectivity(
                main_lo_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(lo_input_index=5)),
                secondary_lo_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(lo_input_index=4)),
            ),
            parameters=api_pb2.SynthIdentity.Parameters(
                low_frequency_filters=[
                    api_pb2.SynthIdentity.Parameters.LowFrequencyFilter(index=0, filter_1="1", filter_2="2")
                ],
                medium_frequency_filter=api_pb2.SynthIdentity.Parameters.ParametrizedFilter(),
                high_frequency_filter=api_pb2.SynthIdentity.Parameters.ParametrizedFilter(),
            ),
        ),
        api_pb2.SynthIdentity(
            index=4,
            connectivity=api_pb2.SynthIdentity.Connectivity(
                # secondary_lo_input=None,
                main_lo_input=api_pb2.RFSource(external_input=api_pb2.ExternalRFInput(demod_lo_input_index=2)),
            ),
            parameters=api_pb2.SynthIdentity.Parameters(
                low_frequency_filters=[
                    api_pb2.SynthIdentity.Parameters.LowFrequencyFilter(index=0, filter_1="1", filter_2="2")
                ],
                medium_frequency_filter=api_pb2.SynthIdentity.Parameters.ParametrizedFilter(),
                high_frequency_filter=api_pb2.SynthIdentity.Parameters.ParametrizedFilter(),
            ),
        ),
    ]

    panel_identity = api_pb2.PanelIdentity(
        rf_outputs=[
            api_pb2.PanelIdentity.RFOutput(
                index=1, source=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=1))
            ),
            api_pb2.PanelIdentity.RFOutput(
                index=2, source=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=2))
            ),
            api_pb2.PanelIdentity.RFOutput(
                index=3, source=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=3))
            ),
            api_pb2.PanelIdentity.RFOutput(
                index=4, source=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=4))
            ),
            api_pb2.PanelIdentity.RFOutput(
                index=5, source=api_pb2.RFSource(rf_up_conv_output=api_pb2.UpConvRFOutput(index=5))
            ),
        ],
        if_output_i=[api_pb2.IFSource(if_downconv_if_source=api_pb2.IFDownConvIFSource(index=0, channel_index=0))],
        if_output_q=[api_pb2.IFSource(if_downconv_if_source=api_pb2.IFDownConvIFSource(index=0, channel_index=1))],
        synth_outputs=[
            api_pb2.PanelIdentity.SynthOutput(
                index=1,
                source=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=3,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_SYNTH,
                    )
                ),
            ),
            api_pb2.PanelIdentity.SynthOutput(
                index=2,
                source=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=6,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_SYNTH,
                    )
                ),
            ),
            api_pb2.PanelIdentity.SynthOutput(
                index=3,
                source=api_pb2.RFSource(
                    synth_output=api_pb2.SynthRFOutput(
                        index=5,
                        output_port=api_pb2.SynthRFOutput.OutputPort.OUTPUT_PORT_SYNTH,
                    )
                ),
            ),
        ],
    )
    return api_pb2.IdentifyResponse(
        rf_up_converters=rf_up_converters,
        rf_down_converters=rf_down_converters,
        if_down_converters=if_down_converters,
        synthesizers=synthesizers,
        panel_identity=panel_identity,
    )
