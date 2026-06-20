package com.exacthour.remote

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.exacthour.remote.ui.ExactHourApp
import com.exacthour.remote.ui.theme.ExactHourTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            ExactHourTheme {
                ExactHourApp()
            }
        }
    }
}
